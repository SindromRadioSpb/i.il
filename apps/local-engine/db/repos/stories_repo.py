"""db/repos/stories_repo.py — Story queries for clustering and summary pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiosqlite


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
