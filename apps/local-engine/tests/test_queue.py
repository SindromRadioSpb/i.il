"""tests/test_queue.py — PublishQueueManager integration tests.

Uses real in-memory SQLite + mocked FacebookClient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repos.publish_queue_repo import (
    get_fb_rate_state,
    get_pending_items,
    upsert_fb_rate_state,
)
from publish.facebook import FBAuthError, FacebookClient
from publish.queue import (
    ProcessCounters,
    PublishQueueManager,
    check_rate,
    _update_rate_state,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 2, 28, 10, 0, 0, tzinfo=UTC)
_NOW_ISO = "2026-02-28T10:00:00.000Z"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def _insert_story(
    db,
    story_id: str,
    *,
    title_ru: str = "Test title",
    summary_ru: str = "Test summary body text",
    summary_version: int = 1,
    state: str = "published",
) -> None:
    await db.execute(
        """
        INSERT INTO stories (
          story_id, start_at, last_update_at,
          title_ru, summary_ru, summary_version,
          category, risk_level, state
        ) VALUES (?, ?, ?, ?, ?, ?, 'other', 'low', ?)
        """,
        (story_id, _NOW_ISO, _NOW_ISO, title_ru, summary_ru, summary_version, state),
    )
    await db.commit()


def _fb_mock(*, post_id: str = "123_456") -> FacebookClient:
    fb = MagicMock(spec=FacebookClient)
    fb.post_text = AsyncMock(return_value=post_id)
    fb.post_photo = AsyncMock(return_value=post_id)
    return fb


async def _seed_rate_state(
    db,
    *,
    posts_this_hour: int = 0,
    posts_today: int = 0,
    last_post_at: str | None = None,
    window_start: str = _NOW_ISO,
) -> None:
    lpa = last_post_at or _iso(_NOW - timedelta(hours=1))
    await upsert_fb_rate_state(
        db,
        posts_this_hour=posts_this_hour,
        hour_window_start=window_start,
        posts_today=posts_today,
        day_window_start=window_start,
        last_post_at=lpa,
        updated_at=_NOW_ISO,
    )


# ─────────────────────────────────────────────────────────────────────────────
# check_rate — pure function tests
# ─────────────────────────────────────────────────────────────────────────────


def test_check_rate_ok_with_no_state():
    assert check_rate(None, _NOW, 8, 40, 180) is None


def test_check_rate_ok_below_limits():
    state = {
        "posts_this_hour": 3,
        "hour_window_start": _iso(_NOW - timedelta(minutes=30)),
        "posts_today": 10,
        "day_window_start": _iso(_NOW - timedelta(hours=6)),
        "last_post_at": _iso(_NOW - timedelta(minutes=5)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) is None


def test_check_rate_gap_blocks_when_too_recent():
    state = {
        "last_post_at": _iso(_NOW - timedelta(minutes=2)),  # 2 min < 3 min gap
        "posts_this_hour": 1,
        "hour_window_start": _iso(_NOW - timedelta(minutes=30)),
        "posts_today": 1,
        "day_window_start": _iso(_NOW - timedelta(hours=1)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) == "gap"


def test_check_rate_gap_ok_after_interval():
    state = {
        "last_post_at": _iso(_NOW - timedelta(minutes=4)),  # 4 min > 3 min gap
        "posts_this_hour": 1,
        "hour_window_start": _iso(_NOW - timedelta(minutes=30)),
        "posts_today": 1,
        "day_window_start": _iso(_NOW - timedelta(hours=1)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) is None


def test_check_rate_hourly_blocks_at_limit():
    state = {
        "last_post_at": _iso(_NOW - timedelta(minutes=5)),
        "posts_this_hour": 8,  # at limit
        "hour_window_start": _iso(_NOW - timedelta(minutes=30)),
        "posts_today": 8,
        "day_window_start": _iso(_NOW - timedelta(hours=1)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) == "hourly"


def test_check_rate_hourly_resets_after_window():
    state = {
        "last_post_at": _iso(_NOW - timedelta(minutes=5)),
        "posts_this_hour": 8,
        "hour_window_start": _iso(_NOW - timedelta(hours=2)),  # expired window
        "posts_today": 8,
        "day_window_start": _iso(_NOW - timedelta(hours=2)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) is None


def test_check_rate_daily_blocks_at_limit():
    state = {
        "last_post_at": _iso(_NOW - timedelta(minutes=5)),
        "posts_this_hour": 1,
        "hour_window_start": _iso(_NOW - timedelta(minutes=30)),
        "posts_today": 40,  # at daily limit
        "day_window_start": _iso(_NOW - timedelta(hours=6)),
    }
    assert check_rate(state, _NOW, 8, 40, 180) == "daily"


# ─────────────────────────────────────────────────────────────────────────────
# Enqueue
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_creates_queue_row(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    qid = await mgr.enqueue(db, "s1", 1, _now=_NOW)
    assert qid is not None
    items = await get_pending_items(db, "fb", _NOW_ISO)
    assert len(items) == 1
    assert items[0]["story_id"] == "s1"


async def test_enqueue_idempotent_same_version(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    qid1 = await mgr.enqueue(db, "s1", 1, _now=_NOW)
    qid2 = await mgr.enqueue(db, "s1", 1, _now=_NOW)  # same version → same dedupe key
    assert qid1 == qid2
    items = await get_pending_items(db, "fb", _NOW_ISO)
    assert len(items) == 1


async def test_enqueue_different_version_creates_new_row(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    await mgr.enqueue(db, "s1", 1, _now=_NOW)
    await mgr.enqueue(db, "s1", 2, _now=_NOW)  # different version → different dedupe key
    items = await get_pending_items(db, "fb", _NOW_ISO)
    assert len(items) == 2


# ─────────────────────────────────────────────────────────────────────────────
# process_pending — happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_process_pending_posts_story(db):
    await _insert_story(db, "s1", title_ru="Заголовок", summary_ru="Содержание")
    mgr = PublishQueueManager()
    await mgr.enqueue(db, "s1", 1, _now=_NOW)
    fb = _fb_mock()

    counters = await mgr.process_pending(db, fb, _now=_NOW)

    assert counters.posted == 1
    assert counters.failed == 0
    assert counters.rate_limited == 0
    fb.post_text.assert_awaited_once()


async def test_process_pending_message_contains_title_and_body(db):
    await _insert_story(db, "s1", title_ru="Мой заголовок", summary_ru="Тело текста")
    mgr = PublishQueueManager()
    await mgr.enqueue(db, "s1", 1, _now=_NOW)
    fb = _fb_mock()

    await mgr.process_pending(db, fb, _now=_NOW)

    call_args = fb.post_text.call_args
    message = call_args.args[0]
    assert "Мой заголовок" in message
    assert "Тело текста" in message


async def test_process_pending_marks_item_completed(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    await mgr.enqueue(db, "s1", 1, _now=_NOW)
    fb = _fb_mock()
    await mgr.process_pending(db, fb, _now=_NOW)

    # No pending items remain
    items = await get_pending_items(db, "fb", _NOW_ISO)
    assert len(items) == 0


async def test_process_pending_updates_rate_state(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    await mgr.enqueue(db, "s1", 1, _now=_NOW)
    fb = _fb_mock()
    await mgr.process_pending(db, fb, _now=_NOW)

    state = await get_fb_rate_state(db)
    assert state is not None
    assert state["posts_this_hour"] == 1
    assert state["posts_today"] == 1
    assert state["last_post_at"] == _NOW_ISO


# ─────────────────────────────────────────────────────────────────────────────
# process_pending — rate limiting
# ─────────────────────────────────────────────────────────────────────────────


async def test_rate_limit_hourly_blocks_processing(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager(max_per_hour=8)
    await mgr.enqueue(db, "s1", 1, _now=_NOW)

    hw_start = _iso(_NOW - timedelta(minutes=30))
    await _seed_rate_state(
        db, posts_this_hour=8, posts_today=8,
        last_post_at=_iso(_NOW - timedelta(minutes=5)),
        window_start=hw_start,
    )

    fb = _fb_mock()
    counters = await mgr.process_pending(db, fb, _now=_NOW)

    assert counters.posted == 0
    assert counters.rate_limited == 1
    fb.post_text.assert_not_awaited()


async def test_rate_limit_daily_blocks_processing(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager(max_per_day=40)
    await mgr.enqueue(db, "s1", 1, _now=_NOW)

    hw_start = _iso(_NOW - timedelta(hours=6))
    await _seed_rate_state(
        db, posts_this_hour=1, posts_today=40,
        last_post_at=_iso(_NOW - timedelta(minutes=5)),
        window_start=hw_start,
    )

    fb = _fb_mock()
    counters = await mgr.process_pending(db, fb, _now=_NOW)

    assert counters.posted == 0
    assert counters.rate_limited == 1
    fb.post_text.assert_not_awaited()


async def test_rate_limit_gap_blocks_within_min_interval(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager(min_interval_sec=180)
    await mgr.enqueue(db, "s1", 1, _now=_NOW)

    hw_start = _iso(_NOW - timedelta(minutes=30))
    await _seed_rate_state(
        db, posts_this_hour=1, posts_today=1,
        last_post_at=_iso(_NOW - timedelta(minutes=2)),  # 2 min < 3 min gap
        window_start=hw_start,
    )

    fb = _fb_mock()
    counters = await mgr.process_pending(db, fb, _now=_NOW)

    assert counters.posted == 0
    assert counters.rate_limited == 1
    fb.post_text.assert_not_awaited()


async def test_rate_limited_count_covers_all_blocked_items(db):
    # 3 stories, all blocked by rate limit
    for i in range(3):
        await _insert_story(db, f"s{i}")
        await PublishQueueManager().enqueue(db, f"s{i}", 1, _now=_NOW)

    await _seed_rate_state(
        db, posts_this_hour=8, posts_today=8,
        last_post_at=_iso(_NOW - timedelta(minutes=5)),
        window_start=_iso(_NOW - timedelta(minutes=30)),
    )

    fb = _fb_mock()
    counters = await PublishQueueManager(max_per_hour=8).process_pending(db, fb, _now=_NOW)

    assert counters.rate_limited == 3
    assert counters.posted == 0


# ─────────────────────────────────────────────────────────────────────────────
# process_pending — failure & retry
# ─────────────────────────────────────────────────────────────────────────────


async def test_process_pending_retries_on_transient_error(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    qid = await mgr.enqueue(db, "s1", 1, _now=_NOW)

    fb = _fb_mock()
    fb.post_text = AsyncMock(side_effect=Exception("Connection refused"))

    counters = await mgr.process_pending(db, fb, _now=_NOW)

    assert counters.failed == 1
    assert counters.posted == 0

    # Item should be rescheduled (pending) not permanently failed
    async with db.execute(
        "SELECT status, attempts FROM publish_queue WHERE queue_id = ?", (qid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1


async def test_process_pending_permanent_fail_after_max_attempts(db):
    await _insert_story(db, "s1")
    mgr = PublishQueueManager()
    qid = await mgr.enqueue(db, "s1", 1, _now=_NOW)

    # Manually set attempts to max_attempts - 1 so next failure is final
    await db.execute(
        "UPDATE publish_queue SET attempts = 4 WHERE queue_id = ?", (qid,)
    )
    await db.commit()

    fb = _fb_mock()
    fb.post_text = AsyncMock(side_effect=Exception("Persistent error"))

    counters = await mgr.process_pending(db, fb, _now=_NOW)

    async with db.execute(
        "SELECT status FROM publish_queue WHERE queue_id = ?", (qid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "failed"
    assert counters.failed == 1


async def test_process_pending_stops_on_auth_error(db):
    # Two stories in the queue — auth error on first should stop both
    for i in range(2):
        await _insert_story(db, f"s{i}")
        await PublishQueueManager().enqueue(db, f"s{i}", 1, _now=_NOW)

    fb = _fb_mock()
    fb.post_text = AsyncMock(
        side_effect=FBAuthError(190, "Invalid OAuth access token")
    )

    counters = await PublishQueueManager().process_pending(db, fb, _now=_NOW)

    # First item fails permanently; second is still pending (unprocessed)
    assert counters.failed == 1
    assert counters.posted == 0

    async with db.execute(
        "SELECT status FROM publish_queue WHERE story_id = 's0'"
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "failed"

    async with db.execute(
        "SELECT status FROM publish_queue WHERE story_id = 's1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "pending"
