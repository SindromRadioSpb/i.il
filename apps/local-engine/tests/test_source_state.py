"""tests/test_source_state.py — Per-source scheduling and backoff tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from db.repos.source_state_repo import (
    get_source_state,
    mark_failure,
    mark_success,
    should_fetch,
)


async def test_unknown_source_is_ready(db):
    """A source with no state record is always ready to fetch."""
    assert await should_fetch(db, "unknown_source", min_interval_sec=300) is True


async def test_just_fetched_source_not_ready(db):
    """A source fetched moments ago should not be fetched again."""
    await mark_success(db, "src1", items_found=10)
    # min_interval_sec=3600 (1 hour) — should not be ready immediately
    ready = await should_fetch(db, "src1", min_interval_sec=3600, jitter_pct=0.0)
    assert ready is False


async def test_source_ready_after_interval(db):
    """A source last fetched > min_interval ago should be ready."""
    # Insert a state record with last_fetch_at in the past
    past = (datetime.now(UTC) - timedelta(seconds=400)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    now_str = past  # reuse for updated_at
    await db.execute(
        """
        INSERT INTO source_state (source_id, last_fetch_at, consecutive_failures,
          total_fetches, total_items_found, updated_at)
        VALUES (?, ?, 0, 1, 5, ?)
        """,
        ("src2", past, past),
    )
    await db.commit()
    ready = await should_fetch(db, "src2", min_interval_sec=300, jitter_pct=0.0)
    assert ready is True


async def test_backoff_blocks_fetch(db):
    """A source in backoff period should not be fetched."""
    future = (datetime.now(UTC) + timedelta(seconds=3600)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    await db.execute(
        """
        INSERT INTO source_state (source_id, last_fetch_at, consecutive_failures,
          backoff_until, total_fetches, total_items_found, updated_at)
        VALUES (?, ?, 2, ?, 3, 0, ?)
        """,
        ("src3", now_str, future, now_str),
    )
    await db.commit()
    ready = await should_fetch(db, "src3", min_interval_sec=10, jitter_pct=0.0)
    assert ready is False


async def test_mark_success_resets_failures(db):
    """mark_success should clear consecutive_failures and backoff_until."""
    await mark_failure(db, "src4")
    await mark_failure(db, "src4")
    await mark_success(db, "src4", items_found=5)
    state = await get_source_state(db, "src4")
    assert state is not None
    assert state["consecutive_failures"] == 0
    assert state["backoff_until"] is None


async def test_mark_failure_increments_failures(db):
    await mark_failure(db, "src5")
    state = await get_source_state(db, "src5")
    assert state is not None
    assert state["consecutive_failures"] == 1
    await mark_failure(db, "src5")
    state = await get_source_state(db, "src5")
    assert state["consecutive_failures"] == 2


async def test_mark_failure_sets_backoff(db):
    await mark_failure(db, "src6")
    state = await get_source_state(db, "src6")
    assert state["backoff_until"] is not None  # backoff_until is in the future


async def test_backoff_increases_exponentially(db):
    """Each failure doubles the backoff time."""
    for _ in range(4):
        await mark_failure(db, "src7")
    state = await get_source_state(db, "src7")
    assert state["consecutive_failures"] == 4
    # After 4 failures: min(30 × 2^3, 3600) = 240 seconds
    backoff_until = datetime.fromisoformat(
        str(state["backoff_until"]).replace("Z", "+00:00")
    )
    elapsed = (backoff_until - datetime.now(UTC)).total_seconds()
    assert elapsed > 200  # at least 200 seconds from now


async def test_mark_success_increments_total_fetches(db):
    await mark_success(db, "src8", items_found=15)
    await mark_success(db, "src8", items_found=10)
    state = await get_source_state(db, "src8")
    assert state["total_fetches"] == 2
    assert state["total_items_found"] == 25
