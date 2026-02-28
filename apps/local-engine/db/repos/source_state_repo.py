"""db/repos/source_state_repo.py — Per-source fetch scheduling with backoff."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import aiosqlite

# Maximum backoff: 1 hour
_MAX_BACKOFF_SEC = 3600
# Base backoff multiplier: 30s × 2^failures
_BASE_BACKOFF_SEC = 30


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _now_dt() -> datetime:
    return datetime.now(UTC)


async def should_fetch(
    db: aiosqlite.Connection,
    source_id: str,
    min_interval_sec: int,
    jitter_pct: float = 0.2,
) -> bool:
    """Return True if the source is ready to be fetched now.

    Checks:
    1. backoff_until: if set and in the future, return False
    2. last_fetch_at: if within min_interval_sec × (1 ± jitter_pct), return False
    3. Otherwise: return True (fetch is due)
    """
    now = _now_dt()

    async with db.execute(
        "SELECT last_fetch_at, backoff_until FROM source_state WHERE source_id = ?",
        (source_id,),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return True  # Never fetched — always ready

    # Check backoff
    backoff_until_str: str | None = row["backoff_until"]
    if backoff_until_str:
        try:
            backoff_until = datetime.fromisoformat(backoff_until_str.replace("Z", "+00:00"))
            if now < backoff_until:
                return False
        except ValueError:
            pass

    # Check min interval with jitter
    last_fetch_str: str | None = row["last_fetch_at"]
    if last_fetch_str:
        try:
            last_fetch = datetime.fromisoformat(last_fetch_str.replace("Z", "+00:00"))
            jitter = random.uniform(-jitter_pct, jitter_pct)
            effective_interval = min_interval_sec * (1.0 + jitter)
            elapsed = (now - last_fetch).total_seconds()
            if elapsed < effective_interval:
                return False
        except ValueError:
            pass

    return True


async def mark_success(
    db: aiosqlite.Connection,
    source_id: str,
    items_found: int = 0,
) -> None:
    """Record a successful fetch: reset failure counter and backoff."""
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO source_state (
          source_id, last_fetch_at, last_success_at, consecutive_failures,
          backoff_until, total_fetches, total_items_found, updated_at
        ) VALUES (?, ?, ?, 0, NULL, 1, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
          last_fetch_at        = excluded.last_fetch_at,
          last_success_at      = excluded.last_success_at,
          consecutive_failures = 0,
          backoff_until        = NULL,
          total_fetches        = total_fetches + 1,
          total_items_found    = total_items_found + excluded.total_items_found,
          updated_at           = excluded.updated_at
        """,
        (source_id, now, now, items_found, now),
    )
    await db.commit()


async def mark_failure(
    db: aiosqlite.Connection,
    source_id: str,
) -> None:
    """Record a failed fetch: increment failures and set exponential backoff."""
    now_dt = _now_dt()
    now = _now_iso()

    # Get current failure count
    async with db.execute(
        "SELECT consecutive_failures FROM source_state WHERE source_id = ?",
        (source_id,),
    ) as cur:
        row = await cur.fetchone()

    current_failures = row["consecutive_failures"] if row else 0
    new_failures = current_failures + 1

    # Exponential backoff: min(2^n × BASE, MAX) seconds
    backoff_sec = min(_BASE_BACKOFF_SEC * (2 ** (new_failures - 1)), _MAX_BACKOFF_SEC)
    backoff_until_dt = now_dt + timedelta(seconds=backoff_sec)
    backoff_until = backoff_until_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    await db.execute(
        """
        INSERT INTO source_state (
          source_id, last_fetch_at, consecutive_failures,
          backoff_until, total_fetches, total_items_found, updated_at
        ) VALUES (?, ?, ?, ?, 1, 0, ?)
        ON CONFLICT(source_id) DO UPDATE SET
          last_fetch_at        = excluded.last_fetch_at,
          consecutive_failures = ?,
          backoff_until        = ?,
          total_fetches        = total_fetches + 1,
          updated_at           = excluded.updated_at
        """,
        (source_id, now, new_failures, backoff_until, now, new_failures, backoff_until),
    )
    await db.commit()


async def get_source_state(
    db: aiosqlite.Connection,
    source_id: str,
) -> dict[str, object] | None:
    """Return raw state dict for a source, or None if not found."""
    async with db.execute(
        "SELECT * FROM source_state WHERE source_id = ?",
        (source_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None
