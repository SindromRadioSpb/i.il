"""db/repos/stories_repo.py — Story queries for clustering and summary pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiosqlite

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StoryCandidate:
    story_id: str
    last_update_at: str
    title_he: str  # founding item's title — used as clustering anchor


async def find_recent_stories(
    db: aiosqlite.Connection,
    window_sec: int = 86400,
) -> list[StoryCandidate]:
    """Fetch stories updated within the time window, each with the founding item's title.

    Uses a correlated subquery to get the first-added item per story — the same
    approach as the TS Worker for clustering compatibility.

    Args:
        db: aiosqlite connection.
        window_sec: look-back window in seconds (default 24 h).
    """
    since = (
        (datetime.now(UTC) - timedelta(seconds=window_sec))
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )

    async with db.execute(
        """
        SELECT s.story_id,
               s.last_update_at,
               i.title_he
          FROM stories s
          JOIN story_items si ON si.story_id = s.story_id
            AND si.item_id = (
              SELECT si2.item_id
                FROM story_items si2
               WHERE si2.story_id = s.story_id
               ORDER BY si2.added_at ASC, si2.item_id ASC
               LIMIT 1
            )
          JOIN items i ON i.item_id = si.item_id
         WHERE s.last_update_at >= ?
           AND s.state != 'hidden'
         ORDER BY s.last_update_at DESC
         LIMIT 100
        """,
        (since,),
    ) as cur:
        rows = await cur.fetchall()

    return [
        StoryCandidate(
            story_id=row["story_id"],
            last_update_at=row["last_update_at"],
            title_he=row["title_he"],
        )
        for row in rows
    ]


async def create_story(
    db: aiosqlite.Connection,
    story_id: str,
    start_at: str,
) -> None:
    """Insert a new story row in state=draft."""
    await db.execute(
        """
        INSERT INTO stories
          (story_id, start_at, last_update_at, category, risk_level, state)
        VALUES (?, ?, ?, 'other', 'low', 'draft')
        """,
        (story_id, start_at, start_at),
    )


async def update_story_last_update(
    db: aiosqlite.Connection,
    story_id: str,
    last_update_at: str,
) -> None:
    """Bump last_update_at for a story that gained a new item."""
    await db.execute(
        "UPDATE stories SET last_update_at = ? WHERE story_id = ?",
        (last_update_at, story_id),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Summary pipeline helpers (port of TS stories_repo summary functions)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StoryForSummary:
    story_id: str
    risk_level: str
    summary_hash: str | None


@dataclass
class StoryItemForSummary:
    item_id: str
    title_he: str
    source_id: str
    published_at: str | None
    source_url: str = ""        # original article URL — used as story_url fallback
    snippet_he: str | None = None   # RSS description snippet (optional extra context)


async def get_stories_needing_summary(
    db: aiosqlite.Connection,
    limit: int = 50,
) -> list[StoryForSummary]:
    """Fetch draft stories that need a Russian summary.

    Excludes stories with editorial_hold = 1.
    """
    async with db.execute(
        """
        SELECT story_id, risk_level, summary_hash
          FROM stories
         WHERE state = 'draft'
           AND editorial_hold = 0
         ORDER BY last_update_at DESC
         LIMIT ?
        """,
        (limit,),
    ) as cur:
        rows = await cur.fetchall()

    return [
        StoryForSummary(
            story_id=row["story_id"],
            risk_level=row["risk_level"],
            summary_hash=row["summary_hash"],
        )
        for row in rows
    ]


async def get_story_items_for_summary(
    db: aiosqlite.Connection,
    story_id: str,
) -> list[StoryItemForSummary]:
    """Fetch items for a story, most-recent first (max 10)."""
    async with db.execute(
        """
        SELECT i.item_id,
               i.title_he,
               i.source_id,
               i.published_at,
               i.source_url,
               i.snippet_he
          FROM story_items si
          JOIN items i ON i.item_id = si.item_id
         WHERE si.story_id = ?
         ORDER BY COALESCE(i.published_at, si.added_at) DESC
         LIMIT 10
        """,
        (story_id,),
    ) as cur:
        rows = await cur.fetchall()

    return [
        StoryItemForSummary(
            item_id=row["item_id"],
            title_he=row["title_he"],
            source_id=row["source_id"],
            published_at=row["published_at"],
            source_url=row["source_url"] or "",
            snippet_he=row["snippet_he"],
        )
        for row in rows
    ]


async def update_story_summary(
    db: aiosqlite.Connection,
    story_id: str,
    title_ru: str,
    summary_ru: str,
    summary_hash: str,
    risk_level: str,
    category: str = "other",
    hashtags: str | None = None,
    fb_caption: str | None = None,
) -> None:
    """Persist a generated summary: update story → published + create publication row.

    Port of TS updateStorySummary() — runs as three sequential writes in one commit.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    await db.execute(
        """
        UPDATE stories
           SET title_ru        = ?,
               summary_ru      = ?,
               summary_hash    = ?,
               summary_version = summary_version + 1,
               risk_level      = ?,
               state           = 'published',
               category        = ?,
               hashtags        = ?,
               fb_caption      = ?
         WHERE story_id = ?
        """,
        (title_ru, summary_ru, summary_hash, risk_level, category, hashtags, fb_caption, story_id),
    )
    await db.execute(
        """
        INSERT OR IGNORE INTO publications (story_id, web_status, fb_status)
        VALUES (?, 'pending', 'disabled')
        """,
        (story_id,),
    )
    await db.execute(
        """
        UPDATE publications
           SET web_status = 'published', web_published_at = ?
         WHERE story_id = ?
        """,
        (now, story_id),
    )
    await db.commit()
