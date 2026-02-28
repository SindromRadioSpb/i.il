"""tests/test_cf_sync.py — CloudflareSync integration tests.

Uses real in-memory SQLite + mocked httpx.AsyncClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sync.cf_sync import CloudflareSync, PushCounters


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_NOW_ISO = "2026-02-28T10:00:00.000Z"
_SYNC_URL = "https://cf.example.com/api/v1/sync/stories"
_TOKEN = "test-sync-token"


def _syncer() -> CloudflareSync:
    return CloudflareSync(_SYNC_URL, _TOKEN)


async def _insert_story(
    db,
    story_id: str,
    *,
    state: str = "published",
    synced: bool = False,
) -> None:
    cf_synced_at = _NOW_ISO if synced else None
    await db.execute(
        """
        INSERT INTO stories (
          story_id, start_at, last_update_at, category, risk_level, state,
          title_ru, summary_ru, summary_version, cf_synced_at
        ) VALUES (?, ?, ?, 'other', 'low', ?, 'Test title', 'Test summary', 1, ?)
        """,
        (story_id, _NOW_ISO, _NOW_ISO, state, cf_synced_at),
    )
    await db.commit()


async def _insert_item(db, item_id: str, story_id: str) -> None:
    await db.execute(
        """
        INSERT INTO items (
          item_id, source_id, source_url, normalized_url, item_key,
          title_he, date_confidence, ingested_at
        ) VALUES (?, 'ynet', ?, ?, ?, 'כותרת', 'high', ?)
        """,
        (
            item_id,
            f"https://ynet.co.il/{item_id}",
            f"https://ynet.co.il/{item_id}",
            item_id,
            _NOW_ISO,
        ),
    )
    await db.execute(
        "INSERT INTO story_items (story_id, item_id, added_at) VALUES (?, ?, ?)",
        (story_id, item_id, _NOW_ISO),
    )
    await db.commit()


def _mock_client(response_body: dict, status: int = 200) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json = MagicMock(return_value=response_body)
    response.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


def _error_client(exc: Exception) -> httpx.AsyncClient:
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock(side_effect=exc)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# No-op when nothing to sync
# ─────────────────────────────────────────────────────────────────────────────


async def test_returns_zero_when_no_published_stories(db):
    counters = await _syncer().push_stories(db)
    assert counters.pushed == 0
    assert counters.failed == 0


async def test_returns_zero_when_all_stories_already_synced(db):
    await _insert_story(db, "s1", synced=True)
    counters = await _syncer().push_stories(db)
    assert counters.pushed == 0


async def test_returns_zero_for_draft_stories(db):
    await _insert_story(db, "s1", state="draft")
    counters = await _syncer().push_stories(db)
    assert counters.pushed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_sends_story_in_payload(db):
    await _insert_story(db, "s1")
    client = _mock_client({"ok": True, "synced": 1})
    await _syncer().push_stories(db, client=client)

    client.post.assert_awaited_once()
    payload = client.post.call_args.kwargs["json"]
    assert len(payload["stories"]) == 1
    assert payload["stories"][0]["story_id"] == "s1"


async def test_sends_bearer_auth_header(db):
    await _insert_story(db, "s1")
    client = _mock_client({"ok": True, "synced": 1})
    syncer = CloudflareSync(_SYNC_URL, "my-secret")
    await syncer.push_stories(db, client=client)

    headers = client.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer my-secret"


async def test_returns_pushed_count_on_success(db):
    await _insert_story(db, "s1")
    await _insert_story(db, "s2")
    client = _mock_client({"ok": True, "synced": 2})
    counters = await _syncer().push_stories(db, client=client)
    assert counters.pushed == 2
    assert counters.failed == 0


async def test_marks_stories_synced_after_success(db):
    await _insert_story(db, "s1")
    client = _mock_client({"ok": True, "synced": 1})
    await _syncer().push_stories(db, client=client)

    async with db.execute("SELECT cf_synced_at FROM stories WHERE story_id = 's1'") as cur:
        row = await cur.fetchone()
    assert row["cf_synced_at"] is not None


async def test_does_not_mark_synced_on_ok_false(db):
    await _insert_story(db, "s1")
    client = _mock_client({"ok": False, "synced": 0})
    counters = await _syncer().push_stories(db, client=client)

    assert counters.failed == 1
    async with db.execute("SELECT cf_synced_at FROM stories WHERE story_id = 's1'") as cur:
        row = await cur.fetchone()
    assert row["cf_synced_at"] is None


async def test_only_sends_unsynced_stories(db):
    await _insert_story(db, "s1", synced=True)   # already synced
    await _insert_story(db, "s2", synced=False)  # needs sync
    client = _mock_client({"ok": True, "synced": 1})
    await _syncer().push_stories(db, client=client)

    payload = client.post.call_args.kwargs["json"]
    assert len(payload["stories"]) == 1
    assert payload["stories"][0]["story_id"] == "s2"


async def test_includes_story_items_in_payload(db):
    await _insert_story(db, "s1")
    await _insert_item(db, "item1", "s1")
    client = _mock_client({"ok": True, "synced": 1})
    await _syncer().push_stories(db, client=client)

    payload = client.post.call_args.kwargs["json"]
    items = payload["stories"][0]["items"]
    assert len(items) == 1
    assert items[0]["item_id"] == "item1"
    assert items[0]["title_he"] == "כותרת"
    assert items[0]["source_id"] == "ynet"


async def test_respects_limit_parameter(db):
    for i in range(5):
        await _insert_story(db, f"s{i}")
    client = _mock_client({"ok": True, "synced": 2})
    await _syncer().push_stories(db, limit=2, client=client)

    payload = client.post.call_args.kwargs["json"]
    assert len(payload["stories"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Failure handling
# ─────────────────────────────────────────────────────────────────────────────


async def test_returns_failed_on_http_error(db):
    await _insert_story(db, "s1")
    exc = httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
    client = _error_client(exc)
    counters = await _syncer().push_stories(db, client=client)

    assert counters.failed == 1
    assert counters.pushed == 0


async def test_returns_failed_on_connection_error(db):
    await _insert_story(db, "s1")
    http_client = AsyncMock(spec=httpx.AsyncClient)
    http_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    counters = await _syncer().push_stories(db, client=http_client)

    assert counters.failed == 1


async def test_does_not_mark_synced_on_http_error(db):
    await _insert_story(db, "s1")
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
    client = _error_client(exc)
    await _syncer().push_stories(db, client=client)

    async with db.execute("SELECT cf_synced_at FROM stories WHERE story_id = 's1'") as cur:
        row = await cur.fetchone()
    assert row["cf_synced_at"] is None
