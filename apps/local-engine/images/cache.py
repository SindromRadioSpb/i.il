"""images/cache.py — Download, validate, and cache article images locally.

Flow for ensure_cached():
  1. Check images_cache table for an existing downloaded record.
  2. If found and file still exists → return local path immediately.
  3. Otherwise → download via httpx, validate via Pillow, store to disk.
  4. On any error → upsert a 'failed' record and return None.

Image IDs are sha256(original_url) — deterministic and collision-resistant.
Files are stored at {data_dir}/{image_id[:2]}/{content_hash}.{ext}.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

import aiosqlite
from db.repos.images_repo import get_image_by_url, upsert_image

MAX_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

_ALLOWED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})
_EXT_MAP: dict[str, str] = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_MIME_MAP: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class ImageCacheManager:
    """Manages downloading and caching of article images."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def ensure_cached(
        self,
        db: aiosqlite.Connection,
        *,
        story_id: str | None = None,
        item_id: str | None = None,
        image_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> str | None:
        """Return the local path for the given image URL, downloading if needed.

        Returns None if the image cannot be obtained (network error, invalid
        format, oversized, etc.).  The images_cache table is always updated
        to reflect the final status.
        """
        image_id = hashlib.sha256(image_url.encode()).hexdigest()

        # Return from cache if the local file still exists
        existing = await get_image_by_url(db, image_url)
        if (
            existing
            and existing["status"] == "downloaded"
            and existing["local_path"]
            and Path(existing["local_path"]).exists()
        ):
            return existing["local_path"]

        try:
            return await self._download(
                db, image_id, image_url, story_id, item_id, client, existing
            )
        except Exception:
            await upsert_image(
                db, image_id, item_id, story_id, image_url, status="failed"
            )
            return None

    async def _download(
        self,
        db: aiosqlite.Connection,
        image_id: str,
        image_url: str,
        story_id: str | None,
        item_id: str | None,
        client: httpx.AsyncClient | None,
        existing: dict | None,
    ) -> str | None:
        headers: dict[str, str] = {}
        if existing and existing.get("etag"):
            headers["If-None-Match"] = existing["etag"]

        async def _get(c: httpx.AsyncClient) -> httpx.Response:
            return await c.get(image_url, headers=headers, follow_redirects=True)

        if client is None:
            async with httpx.AsyncClient(timeout=20) as c:
                resp = await _get(c)
        else:
            resp = await _get(client)

        # 304 Not Modified — existing record is still valid
        if resp.status_code == 304:
            if existing and existing.get("local_path"):
                await upsert_image(
                    db, image_id, item_id, story_id, image_url,
                    local_path=existing["local_path"],
                    etag=existing.get("etag"),
                    content_hash=existing.get("content_hash"),
                    width=existing.get("width"),
                    height=existing.get("height"),
                    size_bytes=existing.get("size_bytes"),
                    mime_type=existing.get("mime_type"),
                    status="downloaded",
                )
                return existing["local_path"]
            return None

        resp.raise_for_status()
        data: bytes = resp.content

        if len(data) > MAX_SIZE_BYTES:
            raise ValueError(f"Image too large: {len(data)} bytes")

        # Validate with Pillow (open twice — verify() consumes the stream)
        try:
            probe = Image.open(BytesIO(data))
            probe.verify()
            img = Image.open(BytesIO(data))
            fmt = img.format or ""
            width, height = img.size
        except (UnidentifiedImageError, Exception) as exc:
            raise ValueError(f"Invalid image data: {exc}") from exc

        if fmt not in _ALLOWED_FORMATS:
            raise ValueError(f"Unsupported image format: {fmt!r}")

        ext = _EXT_MAP[fmt]
        mime = _MIME_MAP[fmt]
        content_hash = hashlib.sha256(data).hexdigest()
        new_etag: str | None = resp.headers.get("etag")

        local_path = self.data_dir / image_id[:2] / f"{content_hash}.{ext}"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

        await upsert_image(
            db, image_id, item_id, story_id, image_url,
            local_path=str(local_path),
            etag=new_etag,
            content_hash=content_hash,
            width=width,
            height=height,
            size_bytes=len(data),
            mime_type=mime,
            status="downloaded",
        )

        return str(local_path)
