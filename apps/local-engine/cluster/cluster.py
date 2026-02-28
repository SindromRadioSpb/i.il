"""cluster/cluster.py — Jaccard-based story clustering.

Exact port of apps/worker/src/cluster/cluster.ts.
Algorithm, thresholds, and window MUST remain identical so that the local
engine produces equivalent story groupings to the Cloudflare Worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite

from cluster.tokens import jaccard_similarity, tokenize
from db.repos.stories_repo import (
    create_story,
    find_recent_stories,
    update_story_last_update,
)
from db.repos.story_items_repo import attach_item

# Look back 24 hours for candidate stories.
CLUSTER_WINDOW_SEC: int = 24 * 60 * 60

# Minimum Jaccard similarity required to attach to an existing story.
# Must EXCEED (strict >) the threshold — identical to TS `if (score > bestScore)`.
SIMILARITY_THRESHOLD: float = 0.25


@dataclass
class ClusterItem:
    """Minimal item representation needed for clustering."""

    item_key: str
    title_he: str
    published_at: str | None = None


@dataclass
class ClusterCounters:
    stories_new: int = 0
    stories_updated: int = 0


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def cluster_new_items(
    db: aiosqlite.Connection,
    items: list[ClusterItem],
) -> ClusterCounters:
    """Cluster a list of newly-ingested items into stories.

    Algorithm (per item):
      1. Tokenize item title.
      2. Scan candidate stories (from last 24 h) for highest Jaccard similarity.
      3. If similarity > THRESHOLD → attach item; bump story.last_update_at.
      4. Otherwise → create a new story, attach item.
      5. In-memory candidate map is updated after each attach so that items
         within the same run can match a story created by an earlier item.

    All DB writes are INSERT OR IGNORE / idempotent, so re-running is safe.
    Commits once at the end of the batch.
    """
    if not items:
        return ClusterCounters()

    candidates = await find_recent_stories(db, CLUSTER_WINDOW_SEC)

    # In-memory map: story_id → token set (expanded as items are clustered).
    candidate_tokens: dict[str, frozenset[str]] = {
        c.story_id: tokenize(c.title_he) for c in candidates
    }

    counters = ClusterCounters()
    now = _now_iso()

    for item in items:
        item_tokens = tokenize(item.title_he)

        # Find best-matching story above threshold.
        best_story_id: str | None = None
        best_score = SIMILARITY_THRESHOLD  # must strictly exceed

        for story_id, story_tokens in candidate_tokens.items():
            score = jaccard_similarity(item_tokens, story_tokens)
            if score > best_score:
                best_score = score
                best_story_id = story_id

        if best_story_id is not None:
            attached = await attach_item(db, best_story_id, item.item_key, now)
            if attached:
                await update_story_last_update(db, best_story_id, now)
                # Expand candidate tokens so subsequent items can match.
                existing = candidate_tokens[best_story_id]
                candidate_tokens[best_story_id] = existing | item_tokens
                counters.stories_updated += 1
        else:
            new_story_id = str(uuid4())
            start_at = item.published_at or now
            await create_story(db, new_story_id, start_at)
            await attach_item(db, new_story_id, item.item_key, now)
            # Register new story so later items in this run can match it.
            candidate_tokens[new_story_id] = item_tokens
            counters.stories_new += 1

    await db.commit()
    return counters
