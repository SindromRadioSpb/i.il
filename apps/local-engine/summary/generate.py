"""summary/generate.py — Summary generation pipeline for the local engine.

Orchestrates: draft stories → memoization → Ollama → glossary → guards →
auto-category → hashtags → persist as published.

Key differences from the TS Worker pipeline:
- No time budget: local machine can run as long as needed.
- MAX_SUMMARIES_PER_RUN defaults to 50 (vs 5 in Worker).
- Uses Ollama instead of Gemini/Claude API.
- Auto-generates category and hashtags via Ollama (best-effort).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx
import aiosqlite

from db.repos.errors_repo import record_error
from db.repos.stories_repo import (
    get_stories_needing_summary,
    get_story_items_for_summary,
    update_story_summary,
)
from summary.categories import classify_category, generate_hashtags
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


@dataclass
class SummaryCounters:
    attempted: int = 0
    published: int = 0
    skipped: int = 0
    failed: int = 0


def _memoization_hash(item_ids: list[str], risk_level: str) -> str:
    """Compute a content hash for memoization — identical to TS pipeline.ts.

    Hash input: sorted(item_ids).join(',') + ':' + risk_level
    """
    key = ",".join(sorted(item_ids)) + ":" + risk_level
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


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
        SummaryCounters with attempted/published/skipped/failed.
    """
    counters = SummaryCounters()
    stories = await get_stories_needing_summary(db, limit=max_summaries)

    for story in stories:
        counters.attempted += 1
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

            # Build prompts and call Ollama.
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

            # Guards
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

            # Auto-category + hashtags (best-effort — failures don't block publish)
            category = await classify_category(
                ollama, parsed.title, full_text, client=http_client
            )
            hashtag_list = await generate_hashtags(
                ollama, parsed.title, category, client=http_client
            )
            hashtags_str = " ".join(hashtag_list) if hashtag_list else None

            await update_story_summary(
                db,
                story.story_id,
                parsed.title,
                full_text,
                new_hash,
                story.risk_level,
                category=category,
                hashtags=hashtags_str,
            )
            counters.published += 1

        except Exception as exc:
            await record_error(
                db, run_id, "summary", None, story.story_id, str(exc)
            )
            counters.failed += 1

    return counters
