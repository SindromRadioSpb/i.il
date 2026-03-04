"""summary/generate.py — Summary generation pipeline for the local engine.

Orchestrates: draft stories → memoization → LLM → glossary → guards →
auto-category → hashtags → WOW-story FB caption → persist as published.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

import aiosqlite
import httpx

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
from summary.llm_provider import LLMProvider
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
    llm: LLMProvider,
    items: list,
    risk_level: str,
    *,
    client: httpx.AsyncClient | None = None,
    llm_max_retries: int = 2,
    llm_json_mode: str = "strict",
) -> tuple[str | None, WowCounters]:
    """Generate WOW-story FB caption via 3-pass pipeline (best-effort)."""
    story_url = items[0].source_url if items else ""
    try:
        facts = await extract_facts(
            llm,
            items,
            story_url,
            risk_level,
            client=client,
            max_retries=llm_max_retries,
            json_mode=llm_json_mode,
        )
        if facts is None:
            wc = WowCounters()
            wc.caption_fail = 1
            return None, wc
        return await compose_wow_post(llm, facts, client=client)
    except Exception:
        wc = WowCounters()
        wc.caption_fail = 1
        return None, wc


async def run_summary_pipeline(
    db: aiosqlite.Connection,
    llm: LLMProvider,
    run_id: str,
    *,
    max_summaries: int = 50,
    target_min: int = 400,
    target_max: int = 700,
    llm_max_retries: int = 2,
    llm_json_mode: str = "strict",
    http_client: httpx.AsyncClient | None = None,
    event_bus: object | None = None,
) -> SummaryCounters:
    """Run the full summary pipeline for all pending draft stories."""
    log = get_logger("summary")
    counters = SummaryCounters()
    stories = await get_stories_needing_summary(db, limit=max_summaries)

    if event_bus is not None:
        await event_bus.emit("phase_start", {"total": len(stories)}, phase="summary")

    for idx, story in enumerate(stories):
        counters.attempted += 1
        log.info("story_processing", idx=idx + 1, total=len(stories), story_id=story.story_id[:12])
        if event_bus is not None:
            await event_bus.emit("story_processing", {
                "story_id": story.story_id[:8],
                "idx": idx + 1,
                "total": len(stories),
                "title_sample": None,
            }, phase="summary")

        try:
            items = await get_story_items_for_summary(db, story.story_id)
            if not items:
                counters.skipped += 1
                if event_bus is not None:
                    await event_bus.emit("story_skip", {
                        "story_id": story.story_id[:8],
                        "reason": "no_items",
                    }, phase="summary")
                continue

            new_hash = _memoization_hash([i.item_id for i in items], story.risk_level)
            if story.summary_hash == new_hash:
                counters.skipped += 1
                if event_bus is not None:
                    await event_bus.emit("story_skip", {
                        "story_id": story.story_id[:8],
                        "reason": "memoized",
                    }, phase="summary")
                continue

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

            raw = await llm.chat(system, user, client=http_client)
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

            (cat_result, wow_result) = await asyncio.gather(
                classify_and_tag(
                    llm,
                    parsed.title,
                    full_text,
                    client=http_client,
                    max_retries=llm_max_retries,
                    json_mode=llm_json_mode,
                ),
                _generate_fb_caption(
                    llm,
                    items,
                    story.risk_level,
                    client=http_client,
                    llm_max_retries=llm_max_retries,
                    llm_json_mode=llm_json_mode,
                ),
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

            if event_bus is not None:
                await event_bus.emit("story_ok", {
                    "story_id": story.story_id[:8],
                    "title_ru": parsed.title,
                    "category": category,
                }, phase="summary")

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            await record_error(db, run_id, "summary", None, story.story_id, err_msg)
            counters.failed += 1
            if event_bus is not None:
                await event_bus.emit("story_fail", {
                    "story_id": story.story_id[:8],
                    "error": err_msg,
                }, phase="summary")

    return counters
