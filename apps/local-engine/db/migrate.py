"""db/migrate.py — Apply all DDL migrations on startup.

Idempotent: uses CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
so it is safe to call on every startup regardless of existing schema.
"""

from __future__ import annotations

import logging
import re

import aiosqlite

from db.schema import ALL_DDL

logger = logging.getLogger(__name__)


def _split_statements(ddl: str) -> list[str]:
    """Split a multi-statement DDL string into individual statements."""
    stmts = []
    for raw in ddl.split(";"):
        cleaned = raw.strip()
        if cleaned:
            stmts.append(cleaned)
    return stmts


async def apply_migrations(db: aiosqlite.Connection) -> None:
    """Create all tables and indexes. Safe to call multiple times."""
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA synchronous=NORMAL")

    tables_created = 0
    indexes_created = 0

    for ddl_block in ALL_DDL:
        for stmt in _split_statements(ddl_block):
            try:
                await db.execute(stmt)
                if re.match(r"CREATE TABLE", stmt, re.IGNORECASE):
                    tables_created += 1
                elif re.match(r"CREATE.*INDEX", stmt, re.IGNORECASE):
                    indexes_created += 1
            except Exception as exc:
                logger.error("Migration statement failed: %s | error: %s", stmt[:80], exc)
                raise

    await db.commit()
    logger.info(
        "Migrations applied: tables=%d indexes=%d",
        tables_created,
        indexes_created,
    )
