"""db/repos/story_items_repo.py — Attach items to stories (INSERT OR IGNORE)."""

from __future__ import annotations

import aiosqlite


async def attach_item(
    db: aiosqlite.Connection,
    story_id: str,
    item_id: str,
    added_at: str,
) -> bool:
    """INSERT OR IGNORE an item into a story.

    Idempotent: re-running with already-attached items has no side-effects.

    Returns:
        True if the item was actually inserted (new attachment);
        False if it was already present (IGNORE fired).
    """
    async with db.execute(
        """
        INSERT OR IGNORE INTO story_items (story_id, item_id, added_at, rank)
        VALUES (?, ?, ?, 0)
        """,
        (story_id, item_id, added_at),
    ) as cursor:
        return cursor.rowcount > 0
