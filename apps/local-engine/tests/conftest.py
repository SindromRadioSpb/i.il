"""tests/conftest.py — Shared pytest fixtures."""

from __future__ import annotations

import pytest
import aiosqlite

from db.migrate import apply_migrations


@pytest.fixture
async def db() -> aiosqlite.Connection:
    """Provide an in-memory SQLite database with all migrations applied."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await apply_migrations(conn)
    yield conn
    await conn.close()
