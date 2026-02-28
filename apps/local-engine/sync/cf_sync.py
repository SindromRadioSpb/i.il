"""sync/cf_sync.py — Push published stories to the Cloudflare Worker.

Queries local SQLite for published stories where cf_synced_at IS NULL,
builds the sync payload, POSTs to the Worker's /api/v1/sync/stories endpoint,
and marks stories as synced on success.

The Worker upserts stories into D1 so the Pages site stays current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ─────────────────────────────────────────────────────────────────────────────
# Counters
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PushCounters:
    pushed: int = 0
    failed: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_unsynced_stories(
    db: aiosqlite.Connection,
    limit: int,
) -> list[dict]:
    async with db.execute(
        """
        SELECT story_id, start_at, last_update_at, title_ru, summary_ru,
               category, risk_level, state, summary_version, hashtags
        FROM stories
        WHERE state = 'published' AND cf_synced_at IS NULL
        ORDER BY last_update_at ASC
        LIMIT ?
        """,
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _get_story_items(
    db: aiosqlite.Connection,
    story_id: str,
) -> list[dict]:
    async with db.execute(
        """
        SELECT i.item_id, i.source_id, i.source_url, i.normalized_url, i.item_key,
               i.title_he, i.published_at, i.date_confidence, i.ingested_at
        FROM story_items si
        JOIN items i ON i.item_id = si.item_id
        WHERE si.story_id = ?
        ORDER BY si.added_at ASC
        """,
        (story_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _mark_synced(
    db: aiosqlite.Connection,
    story_ids: list[str],
    synced_at: str,
) -> None:
    for sid in story_ids:
        await db.execute(
            "UPDATE stories SET cf_synced_at = ? WHERE story_id = ?",
            (synced_at, sid),
        )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Sync client
# ─────────────────────────────────────────────────────────────────────────────


class CloudflareSync:
    """Pushes locally-published stories to the Cloudflare Worker D1 database."""

    def __init__(self, sync_url: str, sync_token: str) -> None:
        self.sync_url = sync_url.rstrip("/")
        self.sync_token = sync_token

    async def push_stories(
        self,
        db: aiosqlite.Connection,
        *,
        limit: int = 50,
        client: httpx.AsyncClient | None = None,
    ) -> PushCounters:
        """Push up to `limit` unsynced published stories to the CF Worker.

        Returns PushCounters with pushed/failed counts.
        """
        stories = await _get_unsynced_stories(db, limit=limit)
        if not stories:
            return PushCounters()

        # Build payload including each story's items
        payload_stories = []
        for story in stories:
            items = await _get_story_items(db, story["story_id"])
            payload_stories.append(
                {
                    "story_id": story["story_id"],
                    "start_at": story["start_at"],
                    "last_update_at": story["last_update_at"],
                    "title_ru": story["title_ru"],
                    "summary_ru": story["summary_ru"],
                    "category": story["category"],
                    "risk_level": story["risk_level"],
                    "state": story["state"],
                    "summary_version": story["summary_version"],
                    "hashtags": story["hashtags"],
                    "items": [
                        {
                            "item_id": item["item_id"],
                            "source_id": item["source_id"],
                            "source_url": item["source_url"],
                            "normalized_url": item["normalized_url"],
                            "item_key": item["item_key"],
                            "title_he": item["title_he"],
                            "published_at": item["published_at"],
                            "date_confidence": item["date_confidence"],
                            "ingested_at": item["ingested_at"],
                        }
                        for item in items
                    ],
                }
            )

        payload = {"stories": payload_stories}
        headers = {
            "Authorization": f"Bearer {self.sync_token}",
            "Content-Type": "application/json",
        }

        async def _post(c: httpx.AsyncClient) -> dict:
            resp = await c.post(self.sync_url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

        try:
            if client is None:
                async with httpx.AsyncClient(timeout=30) as c:
                    data = await _post(c)
            else:
                data = await _post(client)

            if data.get("ok"):
                now = _now_iso()
                await _mark_synced(db, [s["story_id"] for s in stories], now)
                pushed = int(data.get("synced", len(stories)))
                return PushCounters(pushed=pushed)
            else:
                return PushCounters(failed=len(stories))

        except Exception:
            return PushCounters(failed=len(stories))
