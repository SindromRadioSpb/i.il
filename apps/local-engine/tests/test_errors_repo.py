"""tests/test_errors_repo.py — Error events repo tests."""

from __future__ import annotations

import pytest

from db.repos.errors_repo import get_errors_for_run, record_error
from db.repos.runs_repo import RunCounters, finish_run, start_run


async def test_record_error_returns_event_id(db):
    await start_run(db, "run-e1")
    event_id = await record_error(db, "run-e1", "ingest", source_id="ynet_main", message="timeout")
    assert isinstance(event_id, str)
    assert len(event_id) == 32  # uuid4 hex


async def test_get_errors_for_run(db):
    await start_run(db, "run-e2")
    await record_error(db, "run-e2", "ingest", source_id="ynet_main", message="HTTP 503")
    await record_error(db, "run-e2", "summary", story_id="story-abc", message="LLM timeout")
    errors = await get_errors_for_run(db, "run-e2")
    assert len(errors) == 2
    phases = {e.phase for e in errors}
    assert phases == {"ingest", "summary"}


async def test_errors_empty_for_clean_run(db):
    await start_run(db, "run-e3")
    ms = await start_run(db, "run-e3-fin")
    await finish_run(db, "run-e3-fin", ms, RunCounters())
    errors = await get_errors_for_run(db, "run-e3-fin")
    assert errors == []


async def test_error_fields_stored_correctly(db):
    await start_run(db, "run-e4")
    await record_error(
        db,
        run_id="run-e4",
        phase="fb_crosspost",
        source_id=None,
        story_id="story-xyz",
        message="auth_error",
        code="190",
    )
    errors = await get_errors_for_run(db, "run-e4")
    assert len(errors) == 1
    e = errors[0]
    assert e.phase == "fb_crosspost"
    assert e.story_id == "story-xyz"
    assert e.code == "190"
    assert e.source_id is None


async def test_errors_isolated_between_runs(db):
    await start_run(db, "run-ea")
    await start_run(db, "run-eb")
    await record_error(db, "run-ea", "ingest", message="error-a")
    await record_error(db, "run-eb", "ingest", message="error-b")

    errors_a = await get_errors_for_run(db, "run-ea")
    errors_b = await get_errors_for_run(db, "run-eb")
    assert len(errors_a) == 1
    assert len(errors_b) == 1
    assert errors_a[0].message == "error-a"
    assert errors_b[0].message == "error-b"
