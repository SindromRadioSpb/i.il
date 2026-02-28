"""db/repos/images_repo.py — CRUD for the images_cache table."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def get_image_by_url(
    db: aiosqlite.Connection,
    original_url: str,
) -> dict | None:
    """Return the cached image record for a URL, or None if not found."""
    image_id = hashlib.sha256(original_url.encode()).hexdigest()
    async with db.execute(
        "SELECT * FROM images_cache WHERE image_id = ?",
        (image_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_image(
    db: aiosqlite.Connection,
    image_id: str,
    item_id: str | None,
    story_id: str | None,
    original_url: str,
    *,
    local_path: str | None = None,
    etag: str | None = None,
    content_hash: str | None = None,
    width: int | None = None,
    height: int | None = None,
    size_bytes: int | None = None,
    mime_type: str | None = None,
    status: str = "pending",
) -> None:
    """Insert or update an image cache record."""
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO images_cache (
          image_id, item_id, story_id, original_url, local_path, etag,
          content_hash, width, height, size_bytes, mime_type, cached_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_id) DO UPDATE SET
          item_id      = excluded.item_id,
          story_id     = excluded.story_id,
          local_path   = excluded.local_path,
          etag         = excluded.etag,
          content_hash = excluded.content_hash,
          width        = excluded.width,
          height       = excluded.height,
          size_bytes   = excluded.size_bytes,
          mime_type    = excluded.mime_type,
          status       = excluded.status
        """,
        (
            image_id, item_id, story_id, original_url, local_path, etag,
            content_hash, width, height, size_bytes, mime_type, now, status,
        ),
    )
    await db.commit()


async def get_story_image(
    db: aiosqlite.Connection,
    story_id: str,
) -> dict | None:
    """Return the first successfully downloaded image for a story."""
    async with db.execute(
        "SELECT * FROM images_cache WHERE story_id = ? AND status = 'downloaded' LIMIT 1",
        (story_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None
