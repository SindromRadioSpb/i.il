"""db/repos/runs_repo.py — Run lifecycle management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class RunCounters:
    sources_ok: int = 0
    sources_failed: int = 0
    items_found: int = 0
    items_new: int = 0
    stories_new: int = 0
    stories_updated: int = 0
    published_web: int = 0
    published_fb: int = 0
    errors_total: int = 0


@dataclass
class RunRow:
    run_id: str
    started_at: str
    finished_at: str | None
    status: str
    sources_ok: int
    sources_failed: int
    items_found: int
    items_new: int
    stories_new: int
    stories_updated: int
    published_web: int
    published_fb: int
    errors_total: int
    duration_ms: int
    error_summary: str | None


async def start_run(db: aiosqlite.Connection, run_id: str) -> int:
    """Insert a run row with status='in_progress'. Returns epoch ms of start."""
    started_at = _now_iso()
    await db.execute(
        """
        INSERT INTO runs (run_id, started_at, status)
        VALUES (?, ?, 'in_progress')
        """,
        (run_id, started_at),
    )
    await db.commit()
    return int(time.time() * 1000)


async def finish_run(
    db: aiosqlite.Connection,
    run_id: str,
    started_at_ms: int,
    counters: RunCounters,
    error_summary: str | None = None,
) -> None:
    """Update run row with final counters and computed status."""
    finished_at = _now_iso()
    duration_ms = int(time.time() * 1000) - started_at_ms

    if counters.errors_total == 0:
        status = "success"
    elif counters.sources_ok > 0 or counters.published_web > 0:
        status = "partial_failure"
    else:
        status = "failure"

    await db.execute(
        """
        UPDATE runs SET
          finished_at    = ?,
          status         = ?,
          sources_ok     = ?,
          sources_failed = ?,
          items_found    = ?,
          items_new      = ?,
          stories_new    = ?,
          stories_updated = ?,
          published_web  = ?,
          published_fb   = ?,
          errors_total   = ?,
          duration_ms    = ?,
          error_summary  = ?
        WHERE run_id = ?
        """,
        (
            finished_at,
            status,
            counters.sources_ok,
            counters.sources_failed,
            counters.items_found,
            counters.items_new,
            counters.stories_new,
            counters.stories_updated,
            counters.published_web,
            counters.published_fb,
            counters.errors_total,
            duration_ms,
            error_summary,
            run_id,
        ),
    )
    await db.commit()


async def get_recent_runs(db: aiosqlite.Connection, limit: int = 20) -> list[RunRow]:
    """Return the most recent runs ordered by started_at DESC."""
    async with db.execute(
        """
        SELECT run_id, started_at, finished_at, status,
               sources_ok, sources_failed, items_found, items_new,
               stories_new, stories_updated, published_web, published_fb,
               errors_total, duration_ms, error_summary
        FROM runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        RunRow(
            run_id=r["run_id"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
            status=r["status"],
            sources_ok=r["sources_ok"],
            sources_failed=r["sources_failed"],
            items_found=r["items_found"],
            items_new=r["items_new"],
            stories_new=r["stories_new"],
            stories_updated=r["stories_updated"],
            published_web=r["published_web"],
            published_fb=r["published_fb"],
            errors_total=r["errors_total"],
            duration_ms=r["duration_ms"],
            error_summary=r["error_summary"],
        )
        for r in rows
    ]


async def get_last_run(db: aiosqlite.Connection) -> RunRow | None:
    """Return the most recent finished run, or None."""
    runs = await get_recent_runs(db, limit=1)
    return runs[0] if runs else None
