"""tests/test_cluster.py — Story clustering integration tests.

Port of apps/worker/test/cluster.test.ts, adapted to use real in-memory
SQLite rather than mocked repos (more confident, no mock framework needed).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cluster.cluster import CLUSTER_WINDOW_SEC, ClusterItem, cluster_new_items
from db.repos.stories_repo import find_recent_stories
from db.repos.story_items_repo import attach_item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_item(db, item_id: str, title_he: str, source_id: str = "src") -> None:
    """Insert a minimal item row so FK constraints on story_items are satisfied."""
    await db.execute(
        """
        INSERT OR IGNORE INTO items (
          item_id, source_id, source_url, normalized_url, item_key,
          title_he, date_confidence, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'low', '2026-02-28T10:00:00.000Z')
        """,
        (
            item_id,
            source_id,
            f"https://example.com/{item_id}",
            f"https://example.com/{item_id}",
            item_id,
            title_he,
        ),
    )
    await db.commit()


def _item(key: str, title: str, published_at: str | None = None) -> ClusterItem:
    return ClusterItem(item_key=key, title_he=title, published_at=published_at)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

async def test_empty_input_returns_zero_counters(db):
    """Empty item list → zero counters, no DB changes."""
    counters = await cluster_new_items(db, [])
    assert counters.stories_new == 0
    assert counters.stories_updated == 0

    candidates = await find_recent_stories(db)
    assert candidates == []


# ---------------------------------------------------------------------------
# New story creation
# ---------------------------------------------------------------------------

async def test_creates_story_when_no_candidates(db):
    await _insert_item(db, "key1", "שריפה גדולה בחיפה")
    counters = await cluster_new_items(db, [_item("key1", "שריפה גדולה בחיפה")])

    assert counters.stories_new == 1
    assert counters.stories_updated == 0

    candidates = await find_recent_stories(db)
    assert len(candidates) == 1


async def test_published_at_used_as_story_start_at(db):
    pub = "2026-02-27T10:00:00.000Z"
    await _insert_item(db, "key1", "שריפה בחיפה")
    await cluster_new_items(db, [_item("key1", "שריפה בחיפה", published_at=pub)])

    async with db.execute("SELECT start_at FROM stories") as cur:
        row = await cur.fetchone()
    assert row["start_at"] == pub


async def test_null_published_at_uses_current_time_as_start_at(db):
    await _insert_item(db, "key1", "שריפה בחיפה")
    await cluster_new_items(db, [_item("key1", "שריפה בחיפה")])

    async with db.execute("SELECT start_at FROM stories") as cur:
        row = await cur.fetchone()
    start = datetime.fromisoformat(row["start_at"].replace("Z", "+00:00"))
    # start_at should be within the last few seconds
    delta = (datetime.now(UTC) - start).total_seconds()
    assert delta < 5


# ---------------------------------------------------------------------------
# Matching existing story
# ---------------------------------------------------------------------------

async def test_similar_item_attaches_to_existing_story(db):
    """Item with similar title attaches to existing story instead of creating new."""
    # First item creates a story
    await _insert_item(db, "key1", "ביבי נפגש עם מנהיגים אירופאים")
    await cluster_new_items(db, [_item("key1", "ביבי נפגש עם מנהיגים אירופאים")])

    # Second item is similar — should attach
    await _insert_item(db, "key2", "ביבי נפגש עם נשיאים אירופאים")
    counters = await cluster_new_items(db, [_item("key2", "ביבי נפגש עם נשיאים אירופאים")])

    assert counters.stories_new == 0
    assert counters.stories_updated == 1

    # Still only one story
    candidates = await find_recent_stories(db)
    assert len(candidates) == 1

    # Both items should be attached to that story
    async with db.execute("SELECT COUNT(*) as cnt FROM story_items") as cur:
        row = await cur.fetchone()
    assert row["cnt"] == 2


async def test_dissimilar_item_creates_new_story(db):
    """Item with dissimilar title creates a separate story."""
    await _insert_item(db, "key1", "שריפה גדולה בחיפה")
    await cluster_new_items(db, [_item("key1", "שריפה גדולה בחיפה")])

    await _insert_item(db, "key2", "רעידת אדמה בתורכיה")
    counters = await cluster_new_items(db, [_item("key2", "רעידת אדמה בתורכיה")])

    assert counters.stories_new == 1
    assert counters.stories_updated == 0

    candidates = await find_recent_stories(db)
    assert len(candidates) == 2


async def test_attach_idempotent_already_attached_not_counted(db):
    """Re-clustering the same item returns storiesUpdated=0 (INSERT OR IGNORE)."""
    await _insert_item(db, "key1", "ביבי נפגש עם מנהיגים אירופאים")
    await cluster_new_items(db, [_item("key1", "ביבי נפגש עם מנהיגים אירופאים")])

    # Same item again — attach_item returns False (already present)
    await _insert_item(db, "key2", "ביבי נפגש עם נשיאים אירופאים")
    counters1 = await cluster_new_items(db, [_item("key2", "ביבי נפגש עם נשיאים אירופאים")])
    assert counters1.stories_updated == 1

    # Cluster key2 again — already attached, no update
    counters2 = await cluster_new_items(db, [_item("key2", "ביבי נפגש עם נשיאים אירופאים")])
    assert counters2.stories_updated == 0
    assert counters2.stories_new == 0


# ---------------------------------------------------------------------------
# Multiple items — in-run story matching
# ---------------------------------------------------------------------------

async def test_second_item_matches_story_created_by_first_item_same_run(db):
    """Items processed in the same run can match stories created earlier in that run."""
    await _insert_item(db, "key1", "ביבי נפגש עם מנהיגים אירופאים")
    await _insert_item(db, "key2", "ביבי נפגש עם נשיאים אירופאים")

    counters = await cluster_new_items(
        db,
        [
            _item("key1", "ביבי נפגש עם מנהיגים אירופאים"),
            _item("key2", "ביבי נפגש עם נשיאים אירופאים"),
        ],
    )

    assert counters.stories_new == 1       # key1 created a story
    assert counters.stories_updated == 1   # key2 attached to it
    # Only one story overall
    candidates = await find_recent_stories(db)
    assert len(candidates) == 1


async def test_two_unrelated_items_create_two_stories(db):
    await _insert_item(db, "key1", "שריפה גדולה בחיפה")
    await _insert_item(db, "key2", "רעידת אדמה בתורכיה")

    counters = await cluster_new_items(
        db,
        [
            _item("key1", "שריפה גדולה בחיפה"),
            _item("key2", "רעידת אדמה בתורכיה"),
        ],
    )

    assert counters.stories_new == 2
    assert counters.stories_updated == 0

    candidates = await find_recent_stories(db)
    assert len(candidates) == 2


async def test_three_items_two_similar_one_different(db):
    """Two similar items → one story; one unrelated item → second story."""
    await _insert_item(db, "k1", "ביבי נפגש עם מנהיגים אירופאים")
    await _insert_item(db, "k2", "ביבי נפגש עם נשיאים אירופאים")
    await _insert_item(db, "k3", "שריפה בחיפה")

    counters = await cluster_new_items(
        db,
        [
            _item("k1", "ביבי נפגש עם מנהיגים אירופאים"),
            _item("k2", "ביבי נפגש עם נשיאים אירופאים"),
            _item("k3", "שריפה בחיפה"),
        ],
    )

    assert counters.stories_new == 2
    assert counters.stories_updated == 1

    candidates = await find_recent_stories(db)
    assert len(candidates) == 2


# ---------------------------------------------------------------------------
# State defaults
# ---------------------------------------------------------------------------

async def test_new_story_state_is_draft(db):
    await _insert_item(db, "key1", "שריפה בחיפה")
    await cluster_new_items(db, [_item("key1", "שריפה בחיפה")])

    async with db.execute("SELECT state, category, risk_level FROM stories") as cur:
        row = await cur.fetchone()
    assert row["state"] == "draft"
    assert row["category"] == "other"
    assert row["risk_level"] == "low"
