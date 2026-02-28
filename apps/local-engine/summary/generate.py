"""summary/generate.py — Summary generation pipeline for the local engine.

Orchestrates: draft stories → memoization → Ollama → glossary → guards →
auto-category → hashtags → WOW-story FB caption → persist as published.

Key differences from the TS Worker pipeline:
- No time budget: local machine can run as long as needed.
- MAX_SUMMARIES_PER_RUN defaults to 50 (vs 5 in Worker).
- Uses Ollama instead of Gemini/Claude API.
- Auto-generates category and hashtags via Ollama (best-effort).
- Generates WOW-story FB caption (3-pass: fact-extract → draft → critic).
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field

import httpx
import aiosqlite

from db.repos.errors_repo import record_error
from db.repos.stories_repo import (
    get_stories_needing_summary,
    get_story_items_for_summary,
    update_story_summary,
)
from observe.logger import get_logger
from summary.categories import classify_and_tag
from summary.fact_extract import extract_facts
from summary.format import format_body, format_full, parse_sections
from summary.glossary import apply_glossary
from summary.guards import (
    guard_forbidden_words,
    guard_high_risk,
    guard_length,
    guard_numbers,
)
from summary.ollama import OllamaClient
from summary.prompt import SummaryItem, build_system_prompt, build_user_message
from summary.wow_story import WowCounters, compose_wow_post


@dataclass
class SummaryCounters:
    attempted: int = 0
    published: int = 0
    skipped: int = 0
    failed: int = 0
    # WOW-story FB caption stats (best-effort — never block publish)
    wow_caption_ok: int = 0
    wow_caption_fail: int = 0
    wow_rewrite_attempts: int = 0


def _memoization_hash(item_ids: list[str], risk_level: str) -> str:
    """Compute a content hash for memoization — identical to TS pipeline.ts.

    Hash input: sorted(item_ids).join(',') + ':' + risk_level
    """
    key = ",".join(sorted(item_ids)) + ":" + risk_level
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def _generate_fb_caption(
    ollama: OllamaClient,
    items: list,
    risk_level: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[str | None, WowCounters]:
    """Generate WOW-story FB caption via 3-pass Ollama pipeline (best-effort).

    Uses the first item's source_url as story_url for the "Подробнее →" line.
    Never raises — failures result in (None, counters) and story is published
    without a WOW caption (FB falls back to legacy title + summary format).
    """
    story_url = items[0].source_url if items else ""
    try:
        facts = await extract_facts(
            ollama, items, story_url, risk_level, client=client
        )
        if facts is None:
            wc = WowCounters()
            wc.caption_fail = 1
            return None, wc
        return await compose_wow_post(ollama, facts, client=client)
    except Exception:
        wc = WowCounters()
        wc.caption_fail = 1
        return None, wc


async def run_summary_pipeline(
    db: aiosqlite.Connection,
    ollama: OllamaClient,
    run_id: str,
    *,
    max_summaries: int = 50,
    target_min: int = 400,
    target_max: int = 700,
    http_client: httpx.AsyncClient | None = None,
) -> SummaryCounters:
    """Run the full summary pipeline for all pending draft stories.

    Args:
        db: aiosqlite connection.
        ollama: Configured OllamaClient instance.
        run_id: Current run ID for error recording.
        max_summaries: Max stories to process per call (default 50).
        target_min: Minimum body character length (default 400).
        target_max: Maximum body character length (default 700).
        http_client: Optional shared httpx client (injected for tests).

    Returns:
        SummaryCounters with attempted/published/skipped/failed + WOW stats.
    """
    log = get_logger("summary")
    counters = SummaryCounters()
    stories = await get_stories_needing_summary(db, limit=max_summaries)

    for idx, story in enumerate(stories):
        counters.attempted += 1
        log.info("story_processing", idx=idx + 1, total=len(stories), story_id=story.story_id[:12])
        try:
            items = await get_story_items_for_summary(db, story.story_id)
            if not items:
                counters.skipped += 1
                continue

            # Memoization: skip if this exact content was already summarised.
            new_hash = _memoization_hash([i.item_id for i in items], story.risk_level)
            if story.summary_hash == new_hash:
                counters.skipped += 1
                continue

            # ── Pass 0: Build prompts and call Ollama (5-section format) ─────
            summary_items = [
                SummaryItem(
                    item_id=i.item_id,
                    title_he=i.title_he,
                    source_id=i.source_id,
                    published_at=i.published_at,
                )
                for i in items
            ]
            system = build_system_prompt(story.risk_level)
            user = build_user_message(summary_items)

            raw = await ollama.chat(system, user, client=http_client)
            glossarized = apply_glossary(raw)
            parsed = parse_sections(glossarized)

            if parsed is None:
                await record_error(
                    db,
                    run_id,
                    "summary",
                    None,
                    story.story_id,
                    "format_parse_failed",
                )
                counters.failed += 1
                continue

            body = format_body(parsed)
            full_text = format_full(parsed)

            # Guards (5-section format)
            guard_results = [
                guard_length(body, target_min, target_max),
                guard_forbidden_words(full_text),
                guard_numbers([i.title_he for i in items], full_text),
                guard_high_risk(body, story.risk_level),
            ]
            first_failed = next((g for g in guard_results if not g.ok), None)
            if first_failed is not None:
                await record_error(
                    db,
                    run_id,
                    "summary",
                    None,
                    story.story_id,
                    first_failed.reason or "guard_failed",
                )
                counters.failed += 1
                continue

            # ── Best-effort enrichment (failures don't block publish) ────────
            # Run category+hashtags concurrently with the WOW pipeline.
            # classify_and_tag uses one combined Ollama call (was 2 sequential),
            # and runs in parallel with the 2-4 WOW Ollama calls.
            (cat_result, wow_result) = await asyncio.gather(
                classify_and_tag(ollama, parsed.title, full_text, client=http_client),
                _generate_fb_caption(ollama, items, story.risk_level, client=http_client),
            )
            category, hashtag_list = cat_result
            hashtags_str = " ".join(hashtag_list) if hashtag_list else None
            fb_caption, wc = wow_result
            counters.wow_caption_ok += wc.caption_ok
            counters.wow_caption_fail += wc.caption_fail
            counters.wow_rewrite_attempts += wc.rewrite_attempts

            await update_story_summary(
                db,
                story.story_id,
                parsed.title,
                full_text,
                new_hash,
                story.risk_level,
                category=category,
                hashtags=hashtags_str,
                fb_caption=fb_caption,
            )
            counters.published += 1

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            await record_error(
                db, run_id, "summary", None, story.story_id, err_msg
            )
            counters.failed += 1

    return counters
