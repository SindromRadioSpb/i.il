"""tests/test_report.py — generate_daily_report() and why_not_published() tests."""

from __future__ import annotations

import pytest

from observe.report import generate_daily_report
from observe.why_not import why_not_published

_DATE = "2026-02-28"
_NOW = f"{_DATE}T10:00:00.000Z"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _insert_story(
    db,
    story_id: str,
    *,
    state: str = "published",
    title_ru: str | None = "Test title",
    summary_ru: str | None = "Test summary",
    cf_synced_at: str | None = None,
    editorial_hold: int = 0,
) -> None:
    await db.execute(
        """
        INSERT INTO stories (
          story_id, start_at, last_update_at, category, risk_level, state,
          title_ru, summary_ru, summary_version, editorial_hold, cf_synced_at
        ) VALUES (?, ?, ?, 'other', 'low', ?, ?, ?, 1, ?, ?)
        """,
        (story_id, _NOW, _NOW, state, title_ru, summary_ru, editorial_hold, cf_synced_at),
    )
    await db.commit()


async def _insert_item(db, item_id: str, story_id: str) -> None:
    await db.execute(
        """
        INSERT INTO items (
          item_id, source_id, source_url, normalized_url, item_key,
          title_he, date_confidence, ingested_at
        ) VALUES (?, 'ynet', ?, ?, ?, 'כותרת', 'high', ?)
        """,
        (item_id, f"https://ynet.co.il/{item_id}", f"https://ynet.co.il/{item_id}",
         item_id, _NOW),
    )
    await db.execute(
        "INSERT INTO story_items (story_id, item_id, added_at) VALUES (?, ?, ?)",
        (story_id, item_id, _NOW),
    )
    await db.commit()


async def _insert_publication(db, story_id: str) -> None:
    await db.execute(
        """
        INSERT INTO publications (story_id, fb_post_id, fb_posted_at, fb_status)
        VALUES (?, 'fb_123', ?, 'posted')
        """,
        (story_id, _NOW),
    )
    await db.commit()


async def _insert_error(db, phase: str = "ingest", msg: str = "oops") -> None:
    import uuid
    run_id = "run-err-test"
    # Ensure parent run exists (FK constraint)
    await db.execute(
        "INSERT OR IGNORE INTO runs (run_id, started_at, status) VALUES (?, ?, 'finished')",
        (run_id, _NOW),
    )
    await db.execute(
        """
        INSERT INTO error_events (event_id, run_id, phase, code, message, created_at)
        VALUES (?, ?, ?, 'RuntimeError', ?, ?)
        """,
        (uuid.uuid4().hex, run_id, phase, msg, _NOW),
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# generate_daily_report()
# ─────────────────────────────────────────────────────────────────────────────


async def test_report_returns_markdown_string(db):
    report = await generate_daily_report(db, _DATE)
    assert isinstance(report, str)
    assert f"# Daily Report — {_DATE}" in report


async def test_report_saves_to_daily_reports_table(db):
    await generate_daily_report(db, _DATE)
    async with db.execute(
        "SELECT report_date FROM daily_reports WHERE report_date = ?", (_DATE,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["report_date"] == _DATE


async def test_report_upserts_on_second_call(db):
    await generate_daily_report(db, _DATE)
    await generate_daily_report(db, _DATE)  # should not raise
    async with db.execute(
        "SELECT COUNT(*) AS n FROM daily_reports WHERE report_date = ?", (_DATE,)
    ) as cur:
        row = await cur.fetchone()
    assert row["n"] == 1


async def test_report_counts_published_stories(db):
    await _insert_story(db, "s1")
    await _insert_story(db, "s2")
    report = await generate_daily_report(db, _DATE)
    assert "2" in report  # 2 stories published


async def test_report_counts_fb_posts(db):
    await _insert_story(db, "s1")
    await _insert_publication(db, "s1")
    report = await generate_daily_report(db, _DATE)
    # FB posts row should show 1
    assert "FB posts" in report


async def test_report_includes_error_section(db):
    await _insert_error(db, "ingest", "fetch failed")
    report = await generate_daily_report(db, _DATE)
    assert "fetch failed" in report or "ingest" in report


async def test_report_shows_no_errors_when_clean(db):
    report = await generate_daily_report(db, _DATE)
    assert "No errors recorded" in report


async def test_report_stores_counts_in_table(db):
    await _insert_story(db, "s1")
    await _insert_publication(db, "s1")
    await _insert_error(db)
    await generate_daily_report(db, _DATE)

    async with db.execute(
        "SELECT stories_published, fb_posts, errors_total FROM daily_reports WHERE report_date = ?",
        (_DATE,),
    ) as cur:
        row = await cur.fetchone()
    assert row["stories_published"] == 1
    assert row["fb_posts"] == 1
    assert row["errors_total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# why_not_published()
# ─────────────────────────────────────────────────────────────────────────────


async def test_why_not_story_not_found(db):
    reasons = await why_not_published(db, "nonexistent")
    assert len(reasons) == 1
    assert "not found" in reasons[0]


async def test_why_not_clean_story_no_reasons(db):
    await _insert_story(db, "s1", cf_synced_at=_NOW)
    await _insert_item(db, "item1", "s1")
    await _insert_publication(db, "s1")
    reasons = await why_not_published(db, "s1")
    assert reasons == []


async def test_why_not_draft_state(db):
    await _insert_story(db, "s1", state="draft")
    reasons = await why_not_published(db, "s1")
    assert any("state" in r for r in reasons)


async def test_why_not_editorial_hold(db):
    await _insert_story(db, "s1", editorial_hold=1)
    reasons = await why_not_published(db, "s1")
    assert any("editorial_hold" in r for r in reasons)


async def test_why_not_missing_summary(db):
    await _insert_story(db, "s1", summary_ru=None)
    reasons = await why_not_published(db, "s1")
    assert any("summary_ru" in r for r in reasons)


async def test_why_not_missing_title(db):
    await _insert_story(db, "s1", title_ru=None)
    reasons = await why_not_published(db, "s1")
    assert any("title_ru" in r for r in reasons)


async def test_why_not_no_items(db):
    await _insert_story(db, "s1")
    reasons = await why_not_published(db, "s1")
    assert any("no items" in r for r in reasons)


async def test_why_not_not_synced_to_cf(db):
    await _insert_story(db, "s1", cf_synced_at=None)
    await _insert_item(db, "item1", "s1")
    reasons = await why_not_published(db, "s1")
    assert any("cf_synced_at" in r for r in reasons)


async def test_why_not_no_publication(db):
    await _insert_story(db, "s1", cf_synced_at=_NOW)
    await _insert_item(db, "item1", "s1")
    # no publication inserted
    reasons = await why_not_published(db, "s1")
    assert any("publication" in r for r in reasons)


async def test_why_not_multiple_failures(db):
    await _insert_story(db, "s1", state="draft", summary_ru=None, cf_synced_at=None)
    reasons = await why_not_published(db, "s1")
    assert len(reasons) >= 3  # state + summary + cf_synced_at + items + publication
