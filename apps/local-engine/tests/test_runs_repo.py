"""tests/test_runs_repo.py — Run lifecycle repo tests."""

from __future__ import annotations

import pytest

from db.repos.runs_repo import RunCounters, finish_run, get_last_run, get_recent_runs, start_run


async def test_start_run_inserts_row(db):
    await start_run(db, "run-001")
    async with db.execute("SELECT status FROM runs WHERE run_id = ?", ("run-001",)) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["status"] == "in_progress"


async def test_finish_run_success(db):
    started_ms = await start_run(db, "run-002")
    counters = RunCounters(sources_ok=5, items_new=30, published_web=3)
    await finish_run(db, "run-002", started_ms, counters)

    async with db.execute(
        "SELECT status, sources_ok, items_new, published_web FROM runs WHERE run_id=?",
        ("run-002",),
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "success"
    assert row["sources_ok"] == 5
    assert row["items_new"] == 30
    assert row["published_web"] == 3


async def test_finish_run_partial_failure(db):
    started_ms = await start_run(db, "run-003")
    counters = RunCounters(sources_ok=3, sources_failed=2, errors_total=2)
    await finish_run(db, "run-003", started_ms, counters)
    row = await get_last_run(db)
    assert row is not None
    assert row.status == "partial_failure"


async def test_finish_run_failure(db):
    started_ms = await start_run(db, "run-004")
    counters = RunCounters(sources_failed=7, errors_total=7)
    await finish_run(db, "run-004", started_ms, counters)
    row = await get_last_run(db)
    assert row is not None
    assert row.status == "failure"


async def test_finish_run_records_duration(db):
    import time
    started_ms = int(time.time() * 1000) - 1500  # 1.5s ago
    await start_run(db, "run-005")
    await finish_run(db, "run-005", started_ms, RunCounters())

    async with db.execute("SELECT duration_ms FROM runs WHERE run_id=?", ("run-005",)) as cur:
        row = await cur.fetchone()
    assert row["duration_ms"] >= 1500


async def test_get_recent_runs_order(db):
    import asyncio
    for i in range(3):
        ms = await start_run(db, f"run-{i:03d}")
        await finish_run(db, f"run-{i:03d}", ms, RunCounters())
        await asyncio.sleep(0.01)  # ensure distinct started_at timestamps
    runs = await get_recent_runs(db)
    assert len(runs) == 3
    # All IDs present (order may vary if timestamps collide in fast machines)
    run_ids = {r.run_id for r in runs}
    assert run_ids == {"run-000", "run-001", "run-002"}
    # Most recent should be last inserted
    assert runs[0].run_id == "run-002"


async def test_get_last_run_empty(db):
    result = await get_last_run(db)
    assert result is None


async def test_finish_run_with_error_summary(db):
    ms = await start_run(db, "run-err")
    counters = RunCounters(errors_total=1)
    await finish_run(db, "run-err", ms, counters, error_summary="Source ynet_main failed")
    row = await get_last_run(db)
    assert row is not None
    assert row.error_summary == "Source ynet_main failed"
