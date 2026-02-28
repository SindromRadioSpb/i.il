"""tests/test_image_cache.py — ImageCacheManager integration tests.

Uses real Pillow to generate minimal valid JPEG/PNG bytes, real in-memory
SQLite (via the db fixture), and mocked httpx.AsyncClient.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image

from db.repos.images_repo import get_image_by_url, get_story_image
from images.cache import ImageCacheManager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _jpeg_bytes(width: int = 10, height: int = 10) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes(width: int = 10, height: int = 10) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(50, 100, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _mock_client(
    data: bytes,
    etag: str | None = None,
    status: int = 200,
) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.content = data
    response.headers = {"etag": etag} if etag else {}
    response.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    return client


def _error_client(exc: Exception) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock(side_effect=exc)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_downloads_jpeg_and_returns_local_path(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(_jpeg_bytes())
    path = await mgr.ensure_cached(
        db, story_id="s1", image_url="https://cdn.example.com/photo.jpg", client=client
    )
    assert path is not None
    assert Path(path).exists()
    assert path.endswith(".jpg")


async def test_downloads_png_and_returns_local_path(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(_png_bytes())
    path = await mgr.ensure_cached(
        db, image_url="https://cdn.example.com/photo.png", client=client
    )
    assert path is not None
    assert path.endswith(".png")


async def test_stores_metadata_in_db(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(_jpeg_bytes())
    url = "https://cdn.example.com/photo.jpg"

    await mgr.ensure_cached(db, story_id="s1", item_id="i1", image_url=url, client=client)

    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["status"] == "downloaded"
    assert row["story_id"] == "s1"
    assert row["item_id"] == "i1"
    assert row["mime_type"] == "image/jpeg"
    assert row["width"] == 10
    assert row["height"] == 10
    assert row["size_bytes"] is not None
    assert row["size_bytes"] > 0


async def test_image_id_is_sha256_of_url(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/photo.jpg"
    client = _mock_client(_jpeg_bytes())

    await mgr.ensure_cached(db, image_url=url, client=client)

    expected_id = hashlib.sha256(url.encode()).hexdigest()
    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["image_id"] == expected_id


async def test_get_story_image_returns_downloaded(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(_jpeg_bytes())
    await mgr.ensure_cached(
        db, story_id="story-abc", image_url="https://cdn.example.com/img.jpg", client=client
    )
    row = await get_story_image(db, "story-abc")
    assert row is not None
    assert row["status"] == "downloaded"


async def test_etag_is_stored_when_server_sends_it(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(_jpeg_bytes(), etag='"abc123"')
    url = "https://cdn.example.com/tagged.jpg"

    await mgr.ensure_cached(db, image_url=url, client=client)

    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["etag"] == '"abc123"'


# ─────────────────────────────────────────────────────────────────────────────
# Cache hit — second call must NOT re-download
# ─────────────────────────────────────────────────────────────────────────────


async def test_returns_cached_path_on_second_call(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/photo.jpg"
    client1 = _mock_client(_jpeg_bytes())
    client2 = _mock_client(_jpeg_bytes())

    path1 = await mgr.ensure_cached(db, image_url=url, client=client1)
    path2 = await mgr.ensure_cached(db, image_url=url, client=client2)

    assert path1 == path2
    client2.get.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# Failure modes
# ─────────────────────────────────────────────────────────────────────────────


async def test_marks_failed_on_invalid_bytes(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client = _mock_client(b"this is definitely not image data")
    url = "https://cdn.example.com/broken.jpg"

    path = await mgr.ensure_cached(db, image_url=url, client=client)

    assert path is None
    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["status"] == "failed"


async def test_marks_failed_on_http_error(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/missing.jpg"
    exc = httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
    client = _error_client(exc)

    path = await mgr.ensure_cached(db, image_url=url, client=client)

    assert path is None
    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["status"] == "failed"


async def test_marks_failed_on_connection_error(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/unreachable.jpg"
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    path = await mgr.ensure_cached(db, image_url=url, client=client)

    assert path is None
    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["status"] == "failed"


async def test_returns_none_for_oversized_image(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/huge.jpg"
    # Fake oversized response (more than 5 MB of zeros)
    big_data = b"\x00" * (5 * 1024 * 1024 + 1)
    client = _mock_client(big_data)

    path = await mgr.ensure_cached(db, image_url=url, client=client)

    assert path is None
    row = await get_image_by_url(db, url)
    assert row is not None
    assert row["status"] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# File layout
# ─────────────────────────────────────────────────────────────────────────────


async def test_file_stored_in_subdirectory_by_image_id_prefix(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    url = "https://cdn.example.com/photo.jpg"
    image_id = hashlib.sha256(url.encode()).hexdigest()
    client = _mock_client(_jpeg_bytes())

    path = await mgr.ensure_cached(db, image_url=url, client=client)

    assert path is not None
    # File must be under {data_dir}/{image_id[:2]}/
    assert Path(path).parent.name == image_id[:2]


async def test_two_different_urls_produce_different_files(db, tmp_path):
    mgr = ImageCacheManager(tmp_path / "images")
    client1 = _mock_client(_jpeg_bytes(width=10, height=10))
    client2 = _mock_client(_jpeg_bytes(width=20, height=20))

    path1 = await mgr.ensure_cached(
        db, image_url="https://cdn.example.com/a.jpg", client=client1
    )
    path2 = await mgr.ensure_cached(
        db, image_url="https://cdn.example.com/b.jpg", client=client2
    )

    assert path1 is not None
    assert path2 is not None
    assert path1 != path2
