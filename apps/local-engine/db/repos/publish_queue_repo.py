"""db/repos/publish_queue_repo.py — CRUD for publish_queue and fb_rate_state tables."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ─────────────────────────────────────────────────────────────────────────────
# publish_queue
# ─────────────────────────────────────────────────────────────────────────────


async def enqueue_story(
    db: aiosqlite.Connection,
    story_id: str,
    channel: str = "fb",
    *,
    fb_dedupe_key: str | None = None,
    priority: int = 0,
    scheduled_at: str | None = None,
) -> str:
    """Insert a story into the publish queue. Idempotent via fb_dedupe_key.

    Returns the queue_id of the row — either newly created or pre-existing
    (when the dedupe key already exists in the table).
    """
    queue_id = uuid4().hex
    now = _now_iso()
    scheduled_at = scheduled_at or now
    await db.execute(
        """
        INSERT OR IGNORE INTO publish_queue (
          queue_id, story_id, channel, status, priority,
          scheduled_at, attempts, max_attempts,
          fb_dedupe_key, backoff_seconds, created_at
        ) VALUES (?, ?, ?, 'pending', ?, ?, 0, 5, ?, 0, ?)
        """,
        (queue_id, story_id, channel, priority, scheduled_at, fb_dedupe_key, now),
    )
    await db.commit()

    if fb_dedupe_key:
        # Return the actual queue_id (new or pre-existing due to dedupe index)
        async with db.execute(
            "SELECT queue_id FROM publish_queue WHERE fb_dedupe_key = ?",
            (fb_dedupe_key,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row["queue_id"]

    return queue_id


async def get_pending_items(
    db: aiosqlite.Connection,
    channel: str,
    now_iso: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Return pending items eligible for processing (scheduled_at <= now)."""
    async with db.execute(
        """
        SELECT * FROM publish_queue
        WHERE channel = ? AND status = 'pending' AND scheduled_at <= ?
        ORDER BY priority DESC, created_at ASC
        LIMIT ?
        """,
        (channel, now_iso, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def mark_started(
    db: aiosqlite.Connection,
    queue_id: str,
    started_at: str,
) -> None:
    await db.execute(
        "UPDATE publish_queue SET status = 'in_progress', started_at = ? WHERE queue_id = ?",
        (started_at, queue_id),
    )
    await db.commit()


async def mark_completed(
    db: aiosqlite.Connection,
    queue_id: str,
    completed_at: str,
) -> None:
    await db.execute(
        "UPDATE publish_queue SET status = 'completed', completed_at = ? WHERE queue_id = ?",
        (completed_at, queue_id),
    )
    await db.commit()


async def reschedule(
    db: aiosqlite.Connection,
    queue_id: str,
    *,
    scheduled_at: str,
    attempts: int,
    last_error: str | None = None,
    permanent_fail: bool = False,
) -> None:
    """Reschedule a failed item for retry or mark it permanently failed."""
    status = "failed" if permanent_fail else "pending"
    await db.execute(
        """
        UPDATE publish_queue
        SET status = ?, scheduled_at = ?, attempts = ?, last_error = ?
        WHERE queue_id = ?
        """,
        (status, scheduled_at, attempts, last_error, queue_id),
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# fb_rate_state (singleton row, id=1)
# ─────────────────────────────────────────────────────────────────────────────


async def get_fb_rate_state(db: aiosqlite.Connection) -> dict | None:
    async with db.execute("SELECT * FROM fb_rate_state WHERE id = 1") as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_fb_rate_state(
    db: aiosqlite.Connection,
    *,
    posts_this_hour: int,
    hour_window_start: str,
    posts_today: int,
    day_window_start: str,
    last_post_at: str,
    updated_at: str,
) -> None:
    await db.execute(
        """
        INSERT INTO fb_rate_state (
          id, posts_this_hour, hour_window_start,
          posts_today, day_window_start, last_post_at, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          posts_this_hour   = excluded.posts_this_hour,
          hour_window_start = excluded.hour_window_start,
          posts_today       = excluded.posts_today,
          day_window_start  = excluded.day_window_start,
          last_post_at      = excluded.last_post_at,
          updated_at        = excluded.updated_at
        """,
        (
            posts_this_hour, hour_window_start,
            posts_today, day_window_start,
            last_post_at, updated_at,
        ),
    )
    await db.commit()
