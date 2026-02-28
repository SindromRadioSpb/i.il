"""tests/test_proof_mode.py — Proof-mode settings and _enqueue_new_fb_posts filters.

All DB tests use the in-memory `db` fixture from conftest.py.
Health-check tests mock httpx / filesystem calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from config.settings import Settings
from main import _enqueue_new_fb_posts, run_health_check
from publish.queue import PublishQueueManager

_NOW = "2026-02-28T10:00:00.000Z"


# ─────────────────────────────────────────────────────────────────────────────
# Settings: proof mode defaults
# ─────────────────────────────────────────────────────────────────────────────


def test_proof_mode_defaults():
    s = Settings(_env_file=None)  # ignore local .env so we test pure defaults
    assert s.fb_proof_mode is False
    assert s.fb_proof_max_posts_per_run == 3
    assert s.fb_proof_require_image is True
    assert s.fb_proof_only_category == ""


def test_proof_mode_from_env(monkeypatch):
    monkeypatch.setenv("FB_PROOF_MODE", "true")
    monkeypatch.setenv("FB_PROOF_MAX_POSTS_PER_RUN", "5")
    monkeypatch.setenv("FB_PROOF_REQUIRE_IMAGE", "false")
    monkeypatch.setenv("FB_PROOF_ONLY_CATEGORY", "security")
    s = Settings()
    assert s.fb_proof_mode is True
    assert s.fb_proof_max_posts_per_run == 5
    assert s.fb_proof_require_image is False
    assert s.fb_proof_only_category == "security"


def test_proof_max_posts_min_bound(monkeypatch):
    monkeypatch.setenv("FB_PROOF_MAX_POSTS_PER_RUN", "0")
    with pytest.raises(Exception):
        Settings()


def test_proof_settings_not_in_safe_repr():
    """Proof settings are non-secret and should be present in safe_repr."""
    s = Settings()
    d = s.safe_repr()
    assert "fb_proof_mode" in d
    assert "fb_proof_max_posts_per_run" in d


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _insert_story(db, story_id: str, category: str = "other") -> None:
    await db.execute(
        """
        INSERT INTO stories (story_id, start_at, last_update_at, state,
                             editorial_hold, category, summary_version)
        VALUES (?, ?, ?, 'published', 0, ?, 1)
        """,
        (story_id, _NOW, _NOW, category),
    )
    await db.execute(
        "INSERT INTO publications (story_id, fb_status) VALUES (?, 'disabled')",
        (story_id,),
    )
    await db.commit()


async def _insert_image(db, story_id: str, status: str = "downloaded") -> None:
    """Insert a row into images_cache for story_id (no FK on images_cache)."""
    await db.execute(
        """
        INSERT INTO images_cache (image_id, story_id, original_url,
                                  local_path, cached_at, status)
        VALUES (?, ?, 'https://example.com/img.jpg',
                'data/images/ab/abc123.jpg', ?, ?)
        """,
        (f"img_{story_id}", story_id, _NOW, status),
    )
    await db.commit()


def _make_queue_mgr() -> PublishQueueManager:
    return PublishQueueManager(max_per_hour=8, max_per_day=40, min_interval_sec=0)


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_new_fb_posts: basic behaviour
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_basic(db):
    await _insert_story(db, "s1")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log)
    assert count == 1
    # publication status updated to 'pending'
    async with db.execute(
        "SELECT fb_status FROM publications WHERE story_id = 's1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["fb_status"] == "pending"


async def test_enqueue_no_duplicate(db):
    """Second call should not re-enqueue the same story."""
    await _insert_story(db, "s1")
    mgr = _make_queue_mgr()
    log = MagicMock()
    await _enqueue_new_fb_posts(db, mgr, log)
    count2 = await _enqueue_new_fb_posts(db, mgr, log)
    # fb_status is now 'pending', so the story is not returned again
    assert count2 == 0


async def test_enqueue_skips_editorial_hold(db):
    await db.execute(
        """
        INSERT INTO stories (story_id, start_at, last_update_at, state,
                             editorial_hold, category, summary_version)
        VALUES ('held', ?, ?, 'published', 1, 'other', 1)
        """,
        (_NOW, _NOW),
    )
    await db.execute(
        "INSERT INTO publications (story_id, fb_status) VALUES ('held', 'disabled')"
    )
    await db.commit()
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log)
    assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_new_fb_posts: require_image filter
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_require_image_skips_without_image(db):
    """require_image=True should skip stories that have no downloaded image."""
    await _insert_story(db, "no_img")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, require_image=True)
    assert count == 0


async def test_enqueue_require_image_includes_with_downloaded_image(db):
    await _insert_story(db, "with_img")
    await _insert_image(db, "with_img", status="downloaded")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, require_image=True)
    assert count == 1


async def test_enqueue_require_image_skips_pending_image(db):
    """A story with status='pending' image does NOT satisfy require_image."""
    await _insert_story(db, "pending_img")
    await _insert_image(db, "pending_img", status="pending")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, require_image=True)
    assert count == 0


async def test_enqueue_without_require_image_includes_all(db):
    """Without require_image, stories without images are still enqueued."""
    await _insert_story(db, "no_img")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, require_image=False)
    assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_new_fb_posts: only_category filter
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_only_category_matches(db):
    await _insert_story(db, "sec", category="security")
    await _insert_story(db, "pol", category="politics")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, only_category="security")
    assert count == 1
    async with db.execute(
        "SELECT fb_status FROM publications WHERE story_id = 'sec'"
    ) as cur:
        row = await cur.fetchone()
    assert row["fb_status"] == "pending"
    # politics story still disabled
    async with db.execute(
        "SELECT fb_status FROM publications WHERE story_id = 'pol'"
    ) as cur:
        row = await cur.fetchone()
    assert row["fb_status"] == "disabled"


async def test_enqueue_only_category_empty_means_all(db):
    await _insert_story(db, "s1", category="security")
    await _insert_story(db, "s2", category="politics")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, only_category="")
    assert count == 2


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_new_fb_posts: limit
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_limit(db):
    for i in range(5):
        await _insert_story(db, f"s{i}")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, limit=2)
    assert count == 2


async def test_enqueue_limit_zero_means_no_limit(db):
    for i in range(5):
        await _insert_story(db, f"s{i}")
    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(db, mgr, log, limit=0)
    assert count == 5


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_new_fb_posts: combined filters
# ─────────────────────────────────────────────="combined"
# ─────────────────────────────────────────────────────────────────────────────


async def test_enqueue_combined_require_image_and_category(db):
    """Only story that has both matching category AND downloaded image is enqueued."""
    await _insert_story(db, "ok", category="security")
    await _insert_image(db, "ok")

    await _insert_story(db, "no_cat", category="politics")
    await _insert_image(db, "no_cat")  # has image but wrong category

    await _insert_story(db, "no_img", category="security")
    # no image for this one

    mgr = _make_queue_mgr()
    log = MagicMock()
    count = await _enqueue_new_fb_posts(
        db, mgr, log, require_image=True, only_category="security"
    )
    assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Health check: DB
# ─────────────────────────────────────────────────────────────────────────────


async def test_health_check_db_ok(tmp_path):
    """Health check succeeds when DB can be created at the given path."""
    db_path = str(tmp_path / "test.db")
    s = Settings(
        database_path=db_path,
        sources_registry_path="../../sources/registry.yaml",
        ollama_base_url="http://localhost:11434",
        fb_posting_enabled=False,
        cf_sync_enabled=False,
    )

    # Patch httpx to prevent real network calls
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"models": [{"name": "qwen2.5:7b-instruct"}]})

    with patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    assert result is True


async def test_health_check_db_fail():
    """Health check fails when DB connection raises an error."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _fail_db(path):
        raise OSError("cannot open database: permission denied")
        yield  # unreachable  # noqa: unreachable

    s = Settings(
        database_path="irrelevant.db",
        ollama_base_url="http://localhost:11434",
        fb_posting_enabled=False,
        cf_sync_enabled=False,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"models": []})

    with patch("main.get_db", _fail_db), \
         patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    assert result is False


async def test_health_check_ollama_unreachable(tmp_path):
    """Health check passes overall if Ollama is down but still reports Ollama FAIL."""
    db_path = str(tmp_path / "test.db")
    s = Settings(
        database_path=db_path,
        ollama_base_url="http://localhost:11434",
        fb_posting_enabled=False,
        cf_sync_enabled=False,
    )

    with patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    # DB is ok, Ollama failed → overall False
    assert result is False


async def test_health_check_fb_token_missing(tmp_path, monkeypatch):
    """Health check fails when FB posting enabled but token missing."""
    db_path = str(tmp_path / "test.db")
    s = Settings(
        database_path=db_path,
        fb_posting_enabled=True,
        fb_page_id="",           # missing
        fb_page_access_token="", # missing
        cf_sync_enabled=False,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={"models": [{"name": s.ollama_model}]}
    )

    with patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    assert result is False


async def test_health_check_fb_disabled_skipped(tmp_path):
    """When FB posting disabled, FB token check is skipped (not a failure)."""
    db_path = str(tmp_path / "test.db")
    s = Settings(
        database_path=db_path,
        fb_posting_enabled=False,
        fb_page_id="",
        fb_page_access_token="",
        cf_sync_enabled=False,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={"models": [{"name": s.ollama_model}]}
    )

    with patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    assert result is True


async def test_health_check_cf_sync_token_missing(tmp_path):
    """Health check fails when CF sync enabled but token missing."""
    db_path = str(tmp_path / "test.db")
    s = Settings(
        database_path=db_path,
        fb_posting_enabled=False,
        cf_sync_enabled=True,
        cf_sync_url="https://example.workers.dev/api/v1/sync/stories",
        cf_sync_token="",  # missing
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={"models": [{"name": s.ollama_model}]}
    )

    with patch("main.load_sources") as mock_load, \
         patch("main.get_enabled_sources") as mock_enabled, \
         patch("httpx.AsyncClient") as mock_client_cls:

        mock_load.return_value = []
        mock_enabled.return_value = []

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        result = await run_health_check(s)

    assert result is False
