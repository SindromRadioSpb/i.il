"""db/repos/items_repo.py — Item upsert (INSERT OR IGNORE)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiosqlite

from ingest.rss import NormalizedEntry


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class UpsertResult:
    found: int              # total items attempted
    inserted: int           # actually new
    new_keys: set[str] = field(default_factory=set)  # item_keys that were new


async def upsert_items(
    db: aiosqlite.Connection,
    entries: list[NormalizedEntry],
    source_id: str,
) -> UpsertResult:
    """INSERT OR IGNORE entries into the items table.

    Idempotent: re-running with same entries produces no duplicates.
    Uses cursor.rowcount after each statement to detect actual inserts.
    """
    ingested_at = _now_iso()
    new_keys: set[str] = set()

    for entry in entries:
        async with db.execute(
            """
            INSERT OR IGNORE INTO items (
              item_id, source_id, source_url, normalized_url, item_key,
              title_he, published_at, date_confidence, snippet_he,
              title_hash, ingested_at, status, enclosure_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                entry.item_key,   # item_id = item_key (deterministic)
                source_id,
                entry.source_url,
                entry.normalized_url,
                entry.item_key,
                entry.title_he,
                entry.published_at,
                entry.date_confidence,
                entry.snippet_he,
                entry.title_hash,
                ingested_at,
                entry.enclosure_url,
            ),
        ) as cursor:
            if cursor.rowcount > 0:
                new_keys.add(entry.item_key)

    await db.commit()

    return UpsertResult(
        found=len(entries),
        inserted=len(new_keys),
        new_keys=new_keys,
    )
