"""tests/test_migrate.py — DB migration correctness."""

from __future__ import annotations

import pytest
import aiosqlite

from db.migrate import apply_migrations


async def _get_tables(db: aiosqlite.Connection) -> set[str]:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ) as cur:
        rows = await cur.fetchall()
    return {r[0] for r in rows}


async def _get_indexes(db: aiosqlite.Connection) -> set[str]:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    ) as cur:
        rows = await cur.fetchall()
    return {r[0] for r in rows}


@pytest.fixture
async def fresh_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    yield conn
    await conn.close()


async def test_all_tables_created(fresh_db):
    await apply_migrations(fresh_db)
    tables = await _get_tables(fresh_db)
    expected = {
        "items", "stories", "story_items", "publications",
        "runs", "run_lock", "error_events",
        "source_state", "images_cache", "publish_queue",
        "fb_rate_state", "metrics", "daily_reports", "item_embeddings",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


async def test_idempotent_rerun(fresh_db):
    """Calling apply_migrations twice must not raise."""
    await apply_migrations(fresh_db)
    await apply_migrations(fresh_db)  # should be a no-op
    tables = await _get_tables(fresh_db)
    assert "items" in tables


async def test_key_indexes_created(fresh_db):
    await apply_migrations(fresh_db)
    indexes = await _get_indexes(fresh_db)
    assert "idx_items_item_key_unique" in indexes
    assert "idx_stories_state_last_update" in indexes
    assert "idx_pq_dedupe" in indexes
    assert "idx_metrics_phase_key" in indexes


async def test_foreign_keys_enabled(fresh_db):
    await apply_migrations(fresh_db)
    async with fresh_db.execute("PRAGMA foreign_keys") as cur:
        row = await cur.fetchone()
    assert row is not None and row[0] == 1


async def test_stories_has_editorial_hold(fresh_db):
    await apply_migrations(fresh_db)
    async with fresh_db.execute("PRAGMA table_info(stories)") as cur:
        cols = {r[1] for r in await cur.fetchall()}
    assert "editorial_hold" in cols


async def test_stories_has_hashtags_and_cf_synced_at(fresh_db):
    await apply_migrations(fresh_db)
    async with fresh_db.execute("PRAGMA table_info(stories)") as cur:
        cols = {r[1] for r in await cur.fetchall()}
    assert "hashtags" in cols
    assert "cf_synced_at" in cols


async def test_items_has_enclosure_url(fresh_db):
    await apply_migrations(fresh_db)
    async with fresh_db.execute("PRAGMA table_info(items)") as cur:
        cols = {r[1] for r in await cur.fetchall()}
    assert "enclosure_url" in cols
