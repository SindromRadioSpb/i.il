"""observe/server.py — Local HTTP server for live cycle monitoring.

Endpoints:
    GET /health         — liveness probe
    GET /status         — JSON snapshot of current run state + DB stats
    GET /stream         — SSE event stream (text/event-stream)
    GET /published      — recent published stories from local SQLite
    DELETE /drafts      — delete all draft stories from local SQLite

Start via: asyncio.create_task(start_server(settings, bus, db_path))
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response, StreamResponse

from observe.events import BUS, EventBus

if TYPE_CHECKING:
    from config.settings import Settings

log = logging.getLogger("observe.server")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
}


def _json(data: object, status: int = 200) -> Response:
    return Response(
        status=status,
        content_type="application/json",
        text=json.dumps(data, ensure_ascii=False),
        headers=CORS_HEADERS,
    )


# ── Route handlers ────────────────────────────────────────────────────────────


async def handle_health(request: Request) -> Response:
    bus: EventBus = request.app["bus"]
    return _json({"ok": True, "engine": bus.state.engine_status})


async def handle_status(request: Request) -> Response:
    bus: EventBus = request.app["bus"]
    db_path: str = request.app["db_path"]

    state_dict = bus.state.to_dict()
    db_stats: dict = {}

    try:
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT state, COUNT(*) as n FROM stories GROUP BY state"
            ) as cur:
                db_stats["stories"] = {r["state"]: r["n"] for r in await cur.fetchall()}
            async with db.execute(
                "SELECT fb_status, COUNT(*) as n FROM publications GROUP BY fb_status"
            ) as cur:
                db_stats["fb"] = {r["fb_status"]: r["n"] for r in await cur.fetchall()}
            async with db.execute(
                "SELECT source_id, consecutive_failures, backoff_until, last_success_at"
                " FROM source_state ORDER BY source_id"
            ) as cur:
                db_stats["sources"] = [
                    {
                        "source_id": r["source_id"],
                        "failures": r["consecutive_failures"],
                        "backoff_until": r["backoff_until"],
                        "last_success": r["last_success_at"],
                    }
                    for r in await cur.fetchall()
                ]
            async with db.execute(
                "SELECT run_id, started_at, finished_at, status,"
                "       sources_ok, sources_failed, items_new,"
                "       stories_new, published_web, published_fb,"
                "       errors_total, duration_ms"
                " FROM runs ORDER BY started_at DESC LIMIT 5"
            ) as cur:
                rows = await cur.fetchall()
                db_stats["recent_runs"] = [dict(r) for r in rows]
    except Exception as exc:
        db_stats["error"] = str(exc)

    return _json({"ok": True, "state": state_dict, "db": db_stats})


async def handle_stream(request: Request) -> StreamResponse:
    """SSE endpoint — streams events as text/event-stream."""
    bus: EventBus = request.app["bus"]

    resp = StreamResponse(
        status=200,
        headers={
            **CORS_HEADERS,
            "Content-Type": "text/event-stream; charset=utf-8",
            "X-Accel-Buffering": "no",   # disable nginx buffering if proxied
        },
    )
    await resp.prepare(request)

    # Send a keepalive comment immediately so the browser knows it's connected
    await resp.write(b": connected\n\n")

    try:
        async for event in bus.subscribe(replay_history=True):
            if request.transport is None or request.transport.is_closing():
                break
            await resp.write(event.to_sse().encode())
            # Keepalive comment every 15 s is handled by the ping task below
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        try:
            await resp.write_eof()
        except Exception:
            pass

    return resp


async def handle_published(request: Request) -> Response:
    """GET /published — recent published stories from local SQLite."""
    db_path: str = request.app["db_path"]
    try:
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT s.story_id, s.title_ru, s.category, s.last_update_at,"
                "       p.fb_status, p.fb_post_id, p.fb_attempts, p.fb_posted_at,"
                "       p.fb_error_last"
                " FROM stories s"
                " LEFT JOIN publications p ON s.story_id = p.story_id"
                " WHERE s.state = 'published'"
                " ORDER BY s.last_update_at DESC LIMIT 50"
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        return _json({"ok": True, "stories": rows})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)}, status=500)


async def handle_delete_drafts(request: Request) -> Response:
    """DELETE /drafts — remove all draft stories from the local SQLite database."""
    db_path: str = request.app["db_path"]
    try:
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("DELETE FROM stories WHERE state = 'draft'")
            deleted = cur.rowcount
            await db.commit()
        log.info(f"Deleted {deleted} local draft stories via API")
        return _json({"ok": True, "deleted": deleted})
    except Exception as exc:
        log.error(f"Failed to delete drafts: {exc}")
        return _json({"ok": False, "error": str(exc)}, status=500)


async def handle_options(request: Request) -> Response:
    return Response(status=204, headers=CORS_HEADERS)


# ── Keepalive task ────────────────────────────────────────────────────────────


async def _keepalive_task(bus: EventBus) -> None:
    """Emit a heartbeat event every 15 seconds so SSE connections stay alive."""
    while True:
        await asyncio.sleep(15)
        await bus.emit("heartbeat", {})


# ── Server lifecycle ──────────────────────────────────────────────────────────


async def start_server(settings: "Settings", db_path: str) -> None:
    """Create and run the aiohttp server. Designed to run as an asyncio task."""
    app = web.Application()
    app["bus"] = BUS
    app["db_path"] = db_path

    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/stream", handle_stream)
    app.router.add_get("/published", handle_published)
    app.router.add_route("DELETE", "/drafts", handle_delete_drafts)
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=settings.local_api_port)

    # Start keepalive task
    asyncio.create_task(_keepalive_task(BUS))

    try:
        await site.start()
        log.info(f"Local API server listening on :{settings.local_api_port}")
        # Run forever until cancelled
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        BUS.unsubscribe_all()
        await runner.cleanup()
        log.info("Local API server stopped")
