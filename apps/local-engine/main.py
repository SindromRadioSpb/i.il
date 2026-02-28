"""main.py — Local Engine: full scheduler loop.

Wires all six phases into a single run cycle:
  1. RSS Ingest + Clustering  (per-source, with per-source backoff)
  2. AI Summary               (Ollama, up to MAX_SUMMARIES_PER_RUN)
  3. Image Cache              (enclosure_url / og:image, Pillow validate)
  4. FB Publish Queue         (rate-limited, only if FB_POSTING_ENABLED=true)
  5. CF Sync                  (push to Worker, only if CF_SYNC_ENABLED=true)

Usage:
    python main.py            # one cycle, then exit
    python main.py --loop     # scheduler loop (SCHEDULER_INTERVAL_SEC interval)
    python main.py --once     # alias for single cycle
    python main.py --proof-fb # proof run: post up to FB_PROOF_MAX_POSTS_PER_RUN stories, exit 0 if >=2 posted
    python main.py --health   # check all dependencies and exit 0 if OK

Press Ctrl+C to stop gracefully.
"""

from __future__ import annotations

import asyncio
import random
import signal
import sys
import time
from uuid import uuid4

import httpx

from cluster.cluster import ClusterItem, cluster_new_items
from config.settings import Settings
from db.connection import get_db
from db.migrate import apply_migrations
from db.repos.errors_repo import record_error
from db.repos.items_repo import upsert_items
from db.repos.runs_repo import RunCounters, finish_run, start_run
from db.repos.source_state_repo import mark_failure, mark_success, should_fetch
from images.cache import ImageCacheManager
from images.og_parser import extract_og_image
from ingest.rss import fetch_rss
from observe.logger import configure_logging, get_logger
from observe.metrics import MetricsRecorder
from publish.facebook import FacebookClient
from publish.queue import PublishQueueManager
from sources.models import Source
from sources.registry import get_enabled_sources, load_sources
from summary.generate import run_summary_pipeline
from summary.ollama import OllamaClient
from sync.cf_sync import CloudflareSync


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1+2: RSS Ingest + Clustering
# ─────────────────────────────────────────────────────────────────────────────


async def _phase_ingest(
    db,
    sources: list[Source],
    http_client: httpx.AsyncClient,
    run_id: str,
    counters: RunCounters,
    log,
    metrics: MetricsRecorder,
) -> None:
    """Fetch RSS feeds and cluster new items into stories."""
    t0 = time.monotonic()

    for source in sources:
        if not await should_fetch(db, source.id, source.throttle.min_interval_sec):
            log.debug("source_skipped", source=source.id, reason="throttle")
            continue

        try:
            entries = await fetch_rss(source, http_client)
            result = await upsert_items(db, entries, source.id)
            await mark_success(db, source.id, items_found=result.found)

            counters.sources_ok += 1
            counters.items_found += result.found
            counters.items_new += result.inserted

            log.info(
                "source_ok",
                source=source.id,
                found=result.found,
                new=result.inserted,
            )

            # Cluster only items that were genuinely new this run
            if result.new_keys:
                new_entries = [e for e in entries if e.item_key in result.new_keys]
                cluster_items = [
                    ClusterItem(
                        item_key=e.item_key,
                        title_he=e.title_he or "",
                        published_at=e.published_at,
                    )
                    for e in new_entries
                    if e.title_he
                ]
                if cluster_items:
                    cc = await cluster_new_items(db, cluster_items)
                    counters.stories_new += cc.stories_new
                    counters.stories_updated += cc.stories_updated
                    log.info(
                        "cluster_ok",
                        source=source.id,
                        stories_new=cc.stories_new,
                        stories_updated=cc.stories_updated,
                    )

        except Exception as exc:
            await mark_failure(db, source.id)
            counters.sources_failed += 1
            counters.errors_total += 1
            await record_error(db, run_id, "ingest", source.id, None, str(exc))
            log.warning("source_error", source=source.id, error=str(exc))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    await metrics.record(db, "ingest", "sources_ok", counters.sources_ok)
    await metrics.record(db, "ingest", "sources_failed", counters.sources_failed)
    await metrics.record(db, "ingest", "items_new", counters.items_new)
    await metrics.record(db, "ingest", "duration_ms", elapsed_ms)
    await metrics.record(db, "cluster", "stories_new", counters.stories_new)
    await metrics.record(db, "cluster", "stories_updated", counters.stories_updated)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: AI Summary
# ─────────────────────────────────────────────────────────────────────────────


async def _phase_summary(
    db,
    settings: Settings,
    ollama: OllamaClient,
    run_id: str,
    counters: RunCounters,
    log,
    metrics: MetricsRecorder,
) -> None:
    """Generate Russian summaries for draft stories via Ollama.

    Uses a dedicated httpx.AsyncClient with OLLAMA_TIMEOUT_SEC — NOT the shared
    RSS client, which has a short 20s timeout unsuitable for LLM generation.
    """
    t0 = time.monotonic()
    try:
        # Ollama needs its own client: generation can take 30–120 s per story.
        async with httpx.AsyncClient(
            timeout=float(settings.ollama_timeout_sec),
            follow_redirects=False,
        ) as ollama_http:
            # Warmup: ensure the model is loaded into VRAM before the pipeline.
            # After 5 min idle, Ollama unloads the model; first call takes ~40s.
            try:
                await ollama.chat("You are a warmup ping.", "Warmup.", client=ollama_http)
                log.debug("ollama_warmed_up")
            except Exception as warmup_exc:
                log.warning("ollama_warmup_failed", error=str(warmup_exc) or type(warmup_exc).__name__)

            sc = await run_summary_pipeline(
                db,
                ollama,
                run_id,
                max_summaries=settings.max_summaries_per_run,
                target_min=settings.summary_target_min,
                target_max=settings.summary_target_max,
                http_client=ollama_http,
            )
        counters.published_web += sc.published
        counters.errors_total += sc.failed

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "summary_done",
            attempted=sc.attempted,
            published=sc.published,
            skipped=sc.skipped,
            failed=sc.failed,
            elapsed_ms=elapsed_ms,
        )
        await metrics.record(db, "summary", "attempted", sc.attempted)
        await metrics.record(db, "summary", "published", sc.published)
        await metrics.record(db, "summary", "skipped", sc.skipped)
        await metrics.record(db, "summary", "failed", sc.failed)
        await metrics.record(db, "summary", "duration_ms", elapsed_ms)

    except Exception as exc:
        counters.errors_total += 1
        await record_error(db, run_id, "summary", None, None, str(exc))
        log.error("summary_phase_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Image Cache
# ─────────────────────────────────────────────────────────────────────────────


async def _phase_images(
    db,
    settings: Settings,
    log,
    metrics: MetricsRecorder,
    http_client: httpx.AsyncClient,
) -> None:
    """Download and validate images for published stories (best-effort)."""
    t0 = time.monotonic()
    try:
        img_mgr = ImageCacheManager(settings.image_cache_dir)

        # Published stories without a cached image yet; take one item per story
        async with db.execute(
            """
            SELECT s.story_id,
                   i.item_id,
                   i.enclosure_url,
                   i.source_url
              FROM stories s
              JOIN story_items si ON si.story_id = s.story_id
              JOIN items i       ON i.item_id   = si.item_id
             WHERE s.state = 'published'
               AND NOT EXISTS (
                     SELECT 1 FROM images_cache ic
                      WHERE ic.story_id = s.story_id
                        AND ic.status   = 'downloaded'
                   )
               AND (i.enclosure_url IS NOT NULL OR i.source_url IS NOT NULL)
             GROUP BY s.story_id
             ORDER BY s.last_update_at DESC
             LIMIT 50
            """
        ) as cur:
            rows = await cur.fetchall()

        downloaded = 0
        failed = 0

        for row in rows:
            image_url: str | None = row["enclosure_url"]

            # Fallback: scrape og:image from the article page
            if not image_url and row["source_url"]:
                image_url = await extract_og_image(row["source_url"], client=http_client)

            if not image_url:
                continue

            path = await img_mgr.ensure_cached(
                db,
                story_id=row["story_id"],
                item_id=row["item_id"],
                image_url=image_url,
                client=http_client,
            )
            if path:
                downloaded += 1
                log.debug("image_cached", story_id=row["story_id"], path=path)
            else:
                failed += 1

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info("images_done", downloaded=downloaded, failed=failed, elapsed_ms=elapsed_ms)
        await metrics.record(db, "images", "downloaded", downloaded)
        await metrics.record(db, "images", "failed", failed)
        await metrics.record(db, "images", "duration_ms", elapsed_ms)

    except Exception as exc:
        log.error("images_phase_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: FB Publish Queue
# ─────────────────────────────────────────────────────────────────────────────


async def _enqueue_new_fb_posts(
    db,
    queue_mgr: PublishQueueManager,
    log,
    *,
    require_image: bool = False,
    only_category: str = "",
    limit: int = 0,
) -> int:
    """Enqueue published stories with fb_status='disabled' into publish_queue.

    Marks each story's publication row as 'pending' after enqueuing so it
    won't be enqueued again on the next cycle.

    Args:
        require_image: If True, only enqueue stories that have a downloaded
            image in images_cache.  Used by --proof-fb mode.
        only_category: If non-empty, only enqueue stories with this category.
            Used by --proof-fb mode.
        limit: Maximum number of stories to enqueue. 0 = no limit.
    """
    query = """
        SELECT s.story_id, s.summary_version
          FROM stories s
          JOIN publications p ON p.story_id = s.story_id
         WHERE s.state          = 'published'
           AND p.fb_status      = 'disabled'
           AND s.editorial_hold = 0
    """
    params: list[object] = []

    if only_category:
        query += " AND s.category = ?"
        params.append(only_category)

    if require_image:
        query += (
            " AND EXISTS ("
            "  SELECT 1 FROM images_cache ic"
            "   WHERE ic.story_id = s.story_id"
            "     AND ic.status   = 'downloaded'"
            " )"
        )

    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()

    count = 0
    for row in rows:
        await queue_mgr.enqueue(db, row["story_id"], row["summary_version"])
        await db.execute(
            "UPDATE publications SET fb_status = 'pending' WHERE story_id = ?",
            (row["story_id"],),
        )
        count += 1

    if count > 0:
        await db.commit()
        log.info("fb_enqueued", count=count)

    return count


async def _phase_fb(
    db,
    settings: Settings,
    run_id: str,
    counters: RunCounters,
    log,
    metrics: MetricsRecorder,
) -> None:
    """Process FB publish queue: enqueue new stories, post pending items.

    In proof mode (settings.fb_proof_mode=True):
      - Only enqueues stories with downloaded images (if fb_proof_require_image)
      - Only enqueues stories matching fb_proof_only_category (if set)
      - Processes at most fb_proof_max_posts_per_run items
    """
    t0 = time.monotonic()
    try:
        fb_client = FacebookClient(
            page_id=settings.fb_page_id,
            page_access_token=settings.fb_page_access_token,
        )
        queue_mgr = PublishQueueManager(
            max_per_hour=settings.fb_max_per_hour,
            max_per_day=settings.fb_max_per_day,
            min_interval_sec=settings.fb_min_interval_sec,
        )

        proof = settings.fb_proof_mode
        await _enqueue_new_fb_posts(
            db,
            queue_mgr,
            log,
            require_image=proof and settings.fb_proof_require_image,
            only_category=settings.fb_proof_only_category if proof else "",
            limit=settings.fb_proof_max_posts_per_run if proof else 0,
        )

        max_process = settings.fb_proof_max_posts_per_run if proof else 50
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as fb_http:
            fc = await queue_mgr.process_pending(
                db, fb_client, http_client=fb_http, max_process=max_process
            )

        counters.published_fb += fc.posted
        counters.errors_total += fc.failed

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "fb_done",
            posted=fc.posted,
            failed=fc.failed,
            rate_limited=fc.rate_limited,
            elapsed_ms=elapsed_ms,
            proof_mode=proof,
        )
        await metrics.record(db, "fb", "posted", fc.posted)
        await metrics.record(db, "fb", "failed", fc.failed)
        await metrics.record(db, "fb", "rate_limited", fc.rate_limited)
        await metrics.record(db, "fb", "duration_ms", elapsed_ms)

    except Exception as exc:
        counters.errors_total += 1
        await record_error(db, run_id, "fb", None, None, str(exc))
        log.error("fb_phase_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6: CF Sync
# ─────────────────────────────────────────────────────────────────────────────


async def _phase_sync(
    db,
    settings: Settings,
    run_id: str,
    counters: RunCounters,
    log,
    metrics: MetricsRecorder,
) -> None:
    """Push published stories to the Cloudflare Worker."""
    t0 = time.monotonic()
    try:
        syncer = CloudflareSync(settings.cf_sync_url, settings.cf_sync_token)
        sc = await syncer.push_stories(db)
        counters.errors_total += sc.failed

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "sync_done",
            pushed=sc.pushed,
            failed=sc.failed,
            elapsed_ms=elapsed_ms,
        )
        await metrics.record(db, "sync", "pushed", sc.pushed)
        await metrics.record(db, "sync", "failed", sc.failed)
        await metrics.record(db, "sync", "duration_ms", elapsed_ms)

    except Exception as exc:
        counters.errors_total += 1
        await record_error(db, run_id, "sync", None, None, str(exc))
        log.error("sync_phase_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Full cycle
# ─────────────────────────────────────────────────────────────────────────────


async def run_cycle(settings: Settings, sources: list[Source]) -> RunCounters:
    """Execute one full ingest → summary → images → fb → sync cycle."""
    log = get_logger("cycle")
    run_id = uuid4().hex
    counters = RunCounters()
    metrics = MetricsRecorder(run_id)

    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_sec=float(settings.ollama_timeout_sec),
    )

    async with get_db(settings.database_path) as db:
        started_at_ms = await start_run(db, run_id)
        log.info("cycle_start", run_id=run_id[:8])

        # One shared HTTP client for ingest + og:image (not Ollama — separate timeout)
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "NewsHub/1.0 (+https://i.il)"},
        ) as http:

            # ── Phase 1+2: Ingest + Cluster ──────────────────────────────────
            await _phase_ingest(db, sources, http, run_id, counters, log, metrics)

            # ── Phase 3: Summary ─────────────────────────────────────────────
            await _phase_summary(db, settings, ollama, run_id, counters, log, metrics)

            # ── Phase 4: Images ──────────────────────────────────────────────
            await _phase_images(db, settings, log, metrics, http)

            # ── Phase 5: FB (optional) ───────────────────────────────────────
            if settings.fb_posting_enabled:
                await _phase_fb(db, settings, run_id, counters, log, metrics)
            else:
                log.debug("fb_skipped", reason="FB_POSTING_ENABLED=false")

            # ── Phase 6: CF Sync (optional) ──────────────────────────────────
            if settings.cf_sync_enabled:
                await _phase_sync(db, settings, run_id, counters, log, metrics)
            else:
                log.debug("sync_skipped", reason="CF_SYNC_ENABLED=false")

        await finish_run(db, run_id, started_at_ms, counters)
        log.info(
            "cycle_done",
            run_id=run_id[:8],
            sources_ok=counters.sources_ok,
            sources_failed=counters.sources_failed,
            items_new=counters.items_new,
            stories_new=counters.stories_new,
            stories_updated=counters.stories_updated,
            published=counters.published_web,
            fb_posts=counters.published_fb,
            errors=counters.errors_total,
        )

    return counters


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler loop
# ─────────────────────────────────────────────────────────────────────────────


async def scheduler_loop(settings: Settings) -> None:
    """Run cycles indefinitely, sleeping SCHEDULER_INTERVAL_SEC between them."""
    log = get_logger("scheduler")
    sources = load_sources(settings.sources_registry_path)
    enabled = get_enabled_sources(sources)

    log.info(
        "scheduler_start",
        sources=len(enabled),
        interval_sec=settings.scheduler_interval_sec,
        jitter_sec=settings.scheduler_jitter_sec,
    )

    stop_event = asyncio.Event()

    def _handle_signal(sig, _frame=None):
        log.info("shutdown_requested", signal=str(sig))
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    cycle = 0
    while not stop_event.is_set():
        cycle += 1
        log.info("cycle_starting", cycle=cycle)

        try:
            await run_cycle(settings, enabled)
        except Exception as exc:
            log.error("cycle_uncaught_error", cycle=cycle, error=str(exc))

        if stop_event.is_set():
            break

        jitter = random.randint(0, settings.scheduler_jitter_sec)
        sleep_sec = settings.scheduler_interval_sec + jitter
        log.info("sleeping", seconds=sleep_sec, next_cycle=cycle + 1)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=float(sleep_sec))
        except asyncio.TimeoutError:
            pass  # Normal wake-up after interval

    log.info("scheduler_stopped", cycles_completed=cycle)


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────


async def run_health_check(settings: Settings) -> bool:
    """Check all dependencies. Prints a status table. Returns True if all pass."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Database
    try:
        async with get_db(settings.database_path) as db:
            await db.execute("SELECT 1")
        checks.append(("DB", True, settings.database_path))
    except Exception as exc:
        checks.append(("DB", False, str(exc)))

    # 2. Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{settings.ollama_base_url}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        model_found = any(settings.ollama_model in n for n in model_names)
        detail = f"reachable, model {'found' if model_found else 'NOT FOUND: ' + settings.ollama_model}"
        checks.append(("Ollama", True, detail))
    except Exception as exc:
        checks.append(("Ollama", False, f"unreachable: {exc}"))

    # 3. Sources registry
    try:
        srcs = load_sources(settings.sources_registry_path)
        enabled = get_enabled_sources(srcs)
        checks.append(("Sources", True, f"{len(enabled)} enabled"))
    except Exception as exc:
        checks.append(("Sources", False, str(exc)))

    # 4. Facebook credentials (presence only — not validated against API)
    if settings.fb_posting_enabled or "--proof-fb" in sys.argv:
        fb_creds_ok = bool(settings.fb_page_id and settings.fb_page_access_token)
        if fb_creds_ok:
            checks.append(("FB Token", True, f"page_id={settings.fb_page_id}, token present"))
        else:
            missing = []
            if not settings.fb_page_id:
                missing.append("FB_PAGE_ID")
            if not settings.fb_page_access_token:
                missing.append("FB_PAGE_ACCESS_TOKEN")
            checks.append(("FB Token", False, f"missing: {', '.join(missing)}"))
    else:
        checks.append(("FB Token", True, "FB posting disabled — skipped"))

    # 5. CF Sync endpoint (presence only)
    if settings.cf_sync_enabled:
        cf_ok = bool(settings.cf_sync_url and settings.cf_sync_token)
        if cf_ok:
            checks.append(("CF Sync", True, f"url configured, token present"))
        else:
            missing = []
            if not settings.cf_sync_url:
                missing.append("CF_SYNC_URL")
            if not settings.cf_sync_token:
                missing.append("CF_SYNC_TOKEN")
            checks.append(("CF Sync", False, f"missing: {', '.join(missing)}"))
    else:
        checks.append(("CF Sync", True, "CF sync disabled — skipped"))

    # Print table
    all_ok = all(ok for _, ok, _ in checks)
    print("\n=== Health Check ===")
    for name, ok, detail in checks:
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {name:<12} {detail}")
    print("===================")
    if all_ok:
        print("All checks passed.\n")
    else:
        failed = [name for name, ok, _ in checks if not ok]
        print(f"FAILED: {', '.join(failed)}\n")

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, settings.log_file)
    log = get_logger("main")

    args = sys.argv[1:]

    # ── --health: dependency check, no cycle ─────────────────────────────────
    if "--health" in args:
        all_ok = asyncio.run(run_health_check(settings))
        sys.exit(0 if all_ok else 1)

    # ── Initialise DB + migrations (all non-health modes) ─────────────────────
    async def _init_db():
        async with get_db(settings.database_path) as db:
            await apply_migrations(db)

    asyncio.run(_init_db())
    log.info("db_ready", path=settings.database_path)

    # ── --proof-fb: single proof cycle ───────────────────────────────────────
    if "--proof-fb" in args:
        # Force FB posting + proof mode on for this run regardless of .env.
        # Set min_interval_sec=0 so multiple posts can succeed in one cycle
        # (queue.py captures `now` once per batch; elapsed is always ~0 between
        # consecutive posts unless the gap is disabled outright).
        # Normal anti-spam limits (8/hr, 40/day) still apply in daemon mode.
        proof_settings = settings.model_copy(
            update={
                "fb_posting_enabled": True,
                "fb_proof_mode": True,
                "fb_min_interval_sec": 0,
            }
        )
        log.info(
            "starting_proof_mode",
            max_posts=proof_settings.fb_proof_max_posts_per_run,
            require_image=proof_settings.fb_proof_require_image,
            only_category=proof_settings.fb_proof_only_category or "(any)",
        )
        srcs = load_sources(proof_settings.sources_registry_path)
        enabled = get_enabled_sources(srcs)
        log.info("sources_loaded", total=len(enabled))
        counters = asyncio.run(run_cycle(proof_settings, enabled))

        # Proof summary (no secrets)
        print("\n=== PROOF RUN SUMMARY ===")
        print(f"  Items new:      {counters.items_new}")
        print(f"  Stories new:    {counters.stories_new}")
        print(f"  Summaries pub:  {counters.published_web}")
        print(f"  FB posts sent:  {counters.published_fb}")
        print(f"  Errors:         {counters.errors_total}")
        print("=========================")

        needed = 2
        if counters.published_fb >= needed:
            print(f"PROOF PASSED: {counters.published_fb} FB posts sent successfully.\n")
            sys.exit(0)
        else:
            print(
                f"PROOF FAILED: only {counters.published_fb}/{needed} posts sent. "
                "Check logs for details.\n"
            )
            sys.exit(1)

    # ── --loop / --daemon: scheduler loop ────────────────────────────────────
    if "--loop" in args or "--daemon" in args:
        log.info("starting_loop_mode")
        asyncio.run(scheduler_loop(settings))
    else:
        # ── default / --once: single cycle ───────────────────────────────────
        log.info("starting_once_mode")
        srcs = load_sources(settings.sources_registry_path)
        enabled = get_enabled_sources(srcs)
        log.info("sources_loaded", total=len(enabled))
        asyncio.run(run_cycle(settings, enabled))


if __name__ == "__main__":
    main()
