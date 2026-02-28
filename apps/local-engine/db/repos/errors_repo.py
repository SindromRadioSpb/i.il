"""db/repos/errors_repo.py — Structured error event logging."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class ErrorRow:
    event_id: str
    run_id: str
    phase: str
    source_id: str | None
    story_id: str | None
    code: str | None
    message: str | None
    created_at: str


async def record_error(
    db: aiosqlite.Connection,
    run_id: str,
    phase: str,
    source_id: str | None = None,
    story_id: str | None = None,
    message: str | None = None,
    code: str | None = None,
) -> str:
    """Insert an error_event row. Returns the new event_id."""
    event_id = uuid.uuid4().hex
    created_at = _now_iso()
    await db.execute(
        """
        INSERT INTO error_events (event_id, run_id, phase, source_id, story_id, code, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, run_id, phase, source_id, story_id, code, message, created_at),
    )
    await db.commit()
    return event_id


async def get_errors_for_run(db: aiosqlite.Connection, run_id: str) -> list[ErrorRow]:
    """Return all error events for a specific run, ordered by created_at."""
    async with db.execute(
        """
        SELECT event_id, run_id, phase, source_id, story_id, code, message, created_at
        FROM error_events
        WHERE run_id = ?
        ORDER BY created_at ASC
        """,
        (run_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    return [
        ErrorRow(
            event_id=r["event_id"],
            run_id=r["run_id"],
            phase=r["phase"],
            source_id=r["source_id"],
            story_id=r["story_id"],
            code=r["code"],
            message=r["message"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
