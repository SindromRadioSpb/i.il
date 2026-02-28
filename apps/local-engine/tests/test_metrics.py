"""tests/test_metrics.py — MetricsRecorder tests."""

from __future__ import annotations

import pytest

from observe.metrics import MetricsRecorder

_RUN_A = "run-aaa"
_RUN_B = "run-bbb"


# ─────────────────────────────────────────────────────────────────────────────
# record() basics
# ─────────────────────────────────────────────────────────────────────────────


async def test_record_inserts_row(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "ingest", "items_new", 10)

    async with db.execute("SELECT * FROM metrics WHERE run_id = ?", (_RUN_A,)) as cur:
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["phase"] == "ingest"
    assert rows[0]["key"] == "items_new"
    assert rows[0]["value"] == pytest.approx(10.0)


async def test_record_without_run_id(db):
    rec = MetricsRecorder()
    await rec.record(db, "cluster", "stories_new", 3)

    async with db.execute(
        "SELECT run_id FROM metrics WHERE phase = 'cluster'",
    ) as cur:
        row = await cur.fetchone()
    assert row["run_id"] is None


async def test_record_run_id_override(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "summary", "published", 5, run_id=_RUN_B)

    async with db.execute("SELECT run_id FROM metrics WHERE phase = 'summary'") as cur:
        row = await cur.fetchone()
    assert row["run_id"] == _RUN_B


async def test_record_float_value(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "ingest", "duration_ms", 1234.567)

    async with db.execute("SELECT value FROM metrics WHERE key = 'duration_ms'") as cur:
        row = await cur.fetchone()
    assert row["value"] == pytest.approx(1234.567)


# ─────────────────────────────────────────────────────────────────────────────
# get_run_metrics()
# ─────────────────────────────────────────────────────────────────────────────


async def test_get_run_metrics_returns_grouped(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "ingest", "items_new", 10)
    await rec.record(db, "ingest", "items_new", 5)  # second record same key
    await rec.record(db, "cluster", "stories_new", 2)

    result = await rec.get_run_metrics(db, _RUN_A)
    assert result["ingest"]["items_new"] == pytest.approx(15.0)
    assert result["cluster"]["stories_new"] == pytest.approx(2.0)


async def test_get_run_metrics_empty_for_unknown_run(db):
    rec = MetricsRecorder()
    result = await rec.get_run_metrics(db, "nonexistent-run")
    assert result == {}


async def test_get_run_metrics_isolates_runs(db):
    rec_a = MetricsRecorder(_RUN_A)
    rec_b = MetricsRecorder(_RUN_B)
    await rec_a.record(db, "ingest", "items_new", 10)
    await rec_b.record(db, "ingest", "items_new", 20)

    result_a = await rec_a.get_run_metrics(db, _RUN_A)
    result_b = await rec_b.get_run_metrics(db, _RUN_B)
    assert result_a["ingest"]["items_new"] == pytest.approx(10.0)
    assert result_b["ingest"]["items_new"] == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
# get_summary()
# ─────────────────────────────────────────────────────────────────────────────


async def test_get_summary_aggregates_all_recent(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "ingest", "items_new", 10)
    await rec.record(db, "ingest", "items_new", 7)
    await rec.record(db, "fb", "posted", 2)

    summary = await rec.get_summary(db, hours=24)
    assert summary["ingest"]["items_new"] == pytest.approx(17.0)
    assert summary["fb"]["posted"] == pytest.approx(2.0)


async def test_get_summary_returns_empty_when_no_data(db):
    rec = MetricsRecorder()
    summary = await rec.get_summary(db, hours=24)
    assert summary == {}


async def test_get_summary_groups_by_phase_and_key(db):
    rec = MetricsRecorder(_RUN_A)
    await rec.record(db, "summary", "attempted", 5)
    await rec.record(db, "summary", "published", 4)
    await rec.record(db, "summary", "failed", 1)

    summary = await rec.get_summary(db, hours=1)
    assert "attempted" in summary["summary"]
    assert "published" in summary["summary"]
    assert "failed" in summary["summary"]
