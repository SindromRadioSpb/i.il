"""tests/test_observe_server.py — local API server handlers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import aiosqlite

from db.migrate import apply_migrations
from observe.server import handle_delete_drafts


async def test_delete_drafts_cascades_related_rows(tmp_path) -> None:
    """Deleting draft stories via local API must cascade to related tables."""
    db_path = tmp_path / "news_hub.db"
    story_id = "s-draft-1"
    item_id = "item-1"
    now = "2026-03-05T00:00:00Z"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(db)
        await db.execute(
            """
            INSERT INTO items (
              item_id, source_id, source_url, normalized_url, item_key,
              title_he, published_at, ingested_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                "src-1",
                "https://example.com/a",
                "https://example.com/a",
                "k-1",
                "he-title",
                now,
                now,
                "new",
            ),
        )
        await db.execute(
            """
            INSERT INTO stories (story_id, start_at, last_update_at, state)
            VALUES (?, ?, ?, 'draft')
            """,
            (story_id, now, now),
        )
        await db.execute(
            "INSERT INTO story_items (story_id, item_id, added_at, rank) VALUES (?, ?, ?, 0)",
            (story_id, item_id, now),
        )
        await db.execute("INSERT INTO publications (story_id) VALUES (?)", (story_id,))
        await db.execute(
            """
            INSERT INTO publish_queue (
              queue_id, story_id, channel, scheduled_at, created_at
            ) VALUES (?, ?, 'fb', ?, ?)
            """,
            ("q-1", story_id, now, now),
        )
        await db.commit()

    req = SimpleNamespace(app={"db_path": str(db_path)})
    resp = await handle_delete_drafts(req)  # type: ignore[arg-type]
    payload = json.loads(resp.text)

    assert resp.status == 200
    assert payload["ok"] is True
    assert payload["deleted"] == 1
    assert payload["cleaned_orphans"]["story_items"] == 0
    assert payload["cleaned_orphans"]["publications"] == 0
    assert payload["cleaned_orphans"]["publish_queue"] == 0

    async with aiosqlite.connect(db_path) as db:
        for table in ("stories", "story_items", "publications", "publish_queue"):
            async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE story_id = ?", (story_id,)) as cur:
                assert (await cur.fetchone())[0] == 0


async def test_delete_drafts_cleans_legacy_orphans(tmp_path) -> None:
    """Endpoint should clean orphan rows left by older local API behavior."""
    db_path = tmp_path / "news_hub.db"
    now = "2026-03-05T00:00:00Z"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(db)
        await db.execute(
            """
            INSERT INTO stories (story_id, start_at, last_update_at, state)
            VALUES ('s-published', ?, ?, 'published')
            """,
            (now, now),
        )
        await db.execute("INSERT INTO publications (story_id) VALUES ('s-published')")
        await db.execute(
            """
            INSERT INTO publish_queue (
              queue_id, story_id, channel, scheduled_at, created_at
            ) VALUES ('q-live', 's-published', 'fb', ?, ?)
            """,
            (now, now),
        )
        await db.execute(
            """
            INSERT INTO items (
              item_id, source_id, source_url, normalized_url, item_key,
              title_he, published_at, ingested_at, status
            ) VALUES ('i-orphan', 'src-o', 'https://example.com/o', 'https://example.com/o', 'k-o', 'he-o', ?, ?, 'new')
            """,
            (now, now),
        )
        await db.execute(
            """
            INSERT INTO stories (story_id, start_at, last_update_at, state)
            VALUES ('s-orphan', ?, ?, 'published')
            """,
            (now, now),
        )
        await db.execute(
            "INSERT INTO story_items (story_id, item_id, added_at, rank) VALUES ('s-orphan', 'i-orphan', ?, 0)",
            (now,),
        )
        await db.execute("INSERT INTO publications (story_id) VALUES ('s-orphan')")
        await db.execute(
            """
            INSERT INTO publish_queue (
              queue_id, story_id, channel, scheduled_at, created_at
            ) VALUES ('q-orphan', 's-orphan', 'fb', ?, ?)
            """,
            (now, now),
        )
        await db.commit()

        # Simulate legacy orphan rows: disable FK checks and remove parent story only.
        await db.execute("PRAGMA foreign_keys=OFF")
        await db.execute("DELETE FROM stories WHERE story_id = 's-orphan'")
        await db.commit()

    req = SimpleNamespace(app={"db_path": str(db_path)})
    resp = await handle_delete_drafts(req)  # type: ignore[arg-type]
    payload = json.loads(resp.text)

    assert resp.status == 200
    assert payload["ok"] is True
    assert payload["cleaned_orphans"]["story_items"] == 1
    assert payload["cleaned_orphans"]["publications"] == 1
    assert payload["cleaned_orphans"]["publish_queue"] == 1

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM story_items WHERE story_id = 's-orphan'") as cur:
            assert (await cur.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM publications WHERE story_id = 's-orphan'") as cur:
            assert (await cur.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM publish_queue WHERE story_id = 's-orphan'") as cur:
            assert (await cur.fetchone())[0] == 0
