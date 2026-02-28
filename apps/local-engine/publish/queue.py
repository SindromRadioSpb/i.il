"""publish/queue.py — Rate-limited FB publish queue.

Rate limits (all configurable):
  - 8 posts per hour (sliding window)
  - 40 posts per day (sliding window)
  - 3-minute minimum gap between consecutive posts

Retry strategy on transient errors:
  - Exponential backoff: min(2^attempts × 60, 3600) seconds
  - Max 5 attempts per item; after that → permanent failure

Auth errors (FBAuthError) bypass retry and stop all processing immediately.

Design choices:
  - _check_rate() is a pure function — easy to unit-test without DB
  - _update_rate_state() is also pure — returns new state dict
  - _now parameter on process_pending() enables deterministic tests
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import aiosqlite

from db.repos.images_repo import get_story_image
from db.repos.publish_queue_repo import (
    enqueue_story,
    get_fb_rate_state,
    get_pending_items,
    mark_completed,
    mark_started,
    reschedule,
    upsert_fb_rate_state,
)
from publish.facebook import FBAuthError, FacebookClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _compute_backoff(attempts: int) -> int:
    """Exponential backoff seconds after `attempts` failures. Capped at 3600."""
    return min(int(2 ** attempts) * 60, 3600)


# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit logic (pure functions — no I/O)
# ─────────────────────────────────────────────────────────────────────────────


def check_rate(
    state: dict | None,
    now: datetime,
    max_per_hour: int,
    max_per_day: int,
    min_interval_sec: int,
) -> str | None:
    """Return None if OK to post, or a reason string if rate limited.

    Reasons: "gap" | "hourly" | "daily"
    """
    if state is None:
        return None

    # Minimum gap between consecutive posts
    if state.get("last_post_at"):
        elapsed = (now - _parse_iso(state["last_post_at"])).total_seconds()
        if elapsed < min_interval_sec:
            return "gap"

    # Hourly limit
    if state.get("hour_window_start"):
        hw = _parse_iso(state["hour_window_start"])
        if (now - hw).total_seconds() < 3600:
            if state["posts_this_hour"] >= max_per_hour:
                return "hourly"

    # Daily limit
    if state.get("day_window_start"):
        dw = _parse_iso(state["day_window_start"])
        if (now - dw).total_seconds() < 86400:
            if state["posts_today"] >= max_per_day:
                return "daily"

    return None


def _update_rate_state(state: dict | None, now: datetime) -> dict:
    """Return a new rate-state dict reflecting one additional post at `now`."""
    now_iso = _iso(now)

    if state is None:
        return {
            "posts_this_hour": 1,
            "hour_window_start": now_iso,
            "posts_today": 1,
            "day_window_start": now_iso,
            "last_post_at": now_iso,
        }

    # Hourly window — reset if expired
    if state.get("hour_window_start") and (
        (now - _parse_iso(state["hour_window_start"])).total_seconds() < 3600
    ):
        posts_this_hour = state["posts_this_hour"] + 1
        hour_window_start = state["hour_window_start"]
    else:
        posts_this_hour = 1
        hour_window_start = now_iso

    # Daily window — reset if expired
    if state.get("day_window_start") and (
        (now - _parse_iso(state["day_window_start"])).total_seconds() < 86400
    ):
        posts_today = state["posts_today"] + 1
        day_window_start = state["day_window_start"]
    else:
        posts_today = 1
        day_window_start = now_iso

    return {
        "posts_this_hour": posts_this_hour,
        "hour_window_start": hour_window_start,
        "posts_today": posts_today,
        "day_window_start": day_window_start,
        "last_post_at": now_iso,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (private)
# ─────────────────────────────────────────────────────────────────────────────


async def _get_story(db: aiosqlite.Connection, story_id: str) -> dict | None:
    async with db.execute(
        "SELECT story_id, title_ru, summary_ru, hashtags FROM stories WHERE story_id = ?",
        (story_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


def _format_message(story: dict) -> str:
    parts = [p for p in (story.get("title_ru"), story.get("summary_ru")) if p]
    if story.get("hashtags"):
        parts.append(story["hashtags"])
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Queue manager
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ProcessCounters:
    posted: int = 0
    failed: int = 0
    rate_limited: int = 0


class PublishQueueManager:
    def __init__(
        self,
        max_per_hour: int = 8,
        max_per_day: int = 40,
        min_interval_sec: int = 180,
    ) -> None:
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self.min_interval_sec = min_interval_sec

    async def enqueue(
        self,
        db: aiosqlite.Connection,
        story_id: str,
        summary_version: int,
        *,
        channel: str = "fb",
        priority: int = 0,
        _now: datetime | None = None,
    ) -> str:
        """Enqueue a story for FB posting. Idempotent via dedupe key.

        The dedupe key is "{story_id}:v{summary_version}" so re-enqueueing
        the same story version is a no-op.  `_now` is injectable for tests.
        """
        fb_dedupe_key = f"{story_id}:v{summary_version}" if channel == "fb" else None
        scheduled_at = _iso(_now) if _now else None
        return await enqueue_story(
            db, story_id, channel,
            fb_dedupe_key=fb_dedupe_key,
            priority=priority,
            scheduled_at=scheduled_at,
        )

    async def process_pending(
        self,
        db: aiosqlite.Connection,
        fb_client: FacebookClient,
        *,
        http_client=None,
        max_process: int = 50,
        _now: datetime | None = None,
    ) -> ProcessCounters:
        """Process pending FB queue items, respecting rate limits.

        `_now` is injectable for deterministic tests.
        """
        counters = ProcessCounters()
        now = _now or datetime.now(UTC)
        now_iso = _iso(now)

        items = await get_pending_items(db, "fb", now_iso, limit=max_process)

        for i, item in enumerate(items):
            # Re-fetch rate state each iteration (updated after each post)
            rate_state = await get_fb_rate_state(db)
            reason = check_rate(
                rate_state, now,
                self.max_per_hour, self.max_per_day, self.min_interval_sec,
            )
            if reason:
                # All remaining items (including this one) are blocked
                counters.rate_limited = len(items) - i
                break

            await mark_started(db, item["queue_id"], now_iso)

            try:
                story = await _get_story(db, item["story_id"])
                if not story:
                    # Story deleted — mark completed silently
                    await mark_completed(db, item["queue_id"], now_iso)
                    continue

                message = _format_message(story)
                image_row = await get_story_image(db, item["story_id"])

                if image_row and image_row.get("local_path"):
                    await fb_client.post_photo(
                        message, image_row["local_path"], client=http_client
                    )
                else:
                    await fb_client.post_text(message, client=http_client)

                await mark_completed(db, item["queue_id"], now_iso)

                new_state = _update_rate_state(rate_state, now)
                await upsert_fb_rate_state(db, updated_at=now_iso, **new_state)

                counters.posted += 1

            except FBAuthError as exc:
                # Auth errors are permanent — stop all processing
                new_attempts = item["attempts"] + 1
                await reschedule(
                    db, item["queue_id"],
                    scheduled_at=now_iso,
                    attempts=new_attempts,
                    last_error=str(exc),
                    permanent_fail=True,
                )
                counters.failed += 1
                break

            except Exception as exc:
                new_attempts = item["attempts"] + 1
                backoff = _compute_backoff(new_attempts)
                next_time = _iso(now + timedelta(seconds=backoff))
                permanent = new_attempts >= item["max_attempts"]
                await reschedule(
                    db, item["queue_id"],
                    scheduled_at=next_time,
                    attempts=new_attempts,
                    last_error=str(exc),
                    permanent_fail=permanent,
                )
                counters.failed += 1

        return counters
