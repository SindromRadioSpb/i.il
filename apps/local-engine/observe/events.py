"""observe/events.py — In-process event bus for live cycle monitoring.

Phases emit structured events; the HTTP server broadcasts them to SSE clients.
Thread-safe via asyncio — all access must happen from the same event loop.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import AsyncIterator


# ── Event ─────────────────────────────────────────────────────────────────────


@dataclass
class Event:
    type: str
    data: dict
    phase: str | None = None
    ts: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")

    def to_sse(self) -> str:
        """Serialise as an SSE data line."""
        import json
        payload = {"type": self.type, "ts": self.ts, "data": self.data}
        if self.phase:
            payload["phase"] = self.phase
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── RunState ──────────────────────────────────────────────────────────────────


@dataclass
class RunCountersSnapshot:
    sources_ok: int = 0
    sources_failed: int = 0
    items_found: int = 0
    items_new: int = 0
    stories_new: int = 0
    stories_updated: int = 0
    published_web: int = 0
    published_fb: int = 0
    errors_total: int = 0


@dataclass
class RunState:
    """Live snapshot of the current (or last) cycle."""
    engine_status: str = "idle"          # idle | running | sleeping
    run_id: str | None = None
    phase: str | None = None             # ingest | summary | images | fb | sync
    phase_detail: str | None = None      # e.g. "story 3/10" or "ynet_main"
    phase_started_at: float = 0.0        # monotonic
    cycle_started_at: float = 0.0        # monotonic
    next_cycle_at: str | None = None     # ISO timestamp when sleeping
    counters: RunCountersSnapshot = field(default_factory=RunCountersSnapshot)
    last_run_status: str | None = None   # success | partial_failure | failure
    last_run_elapsed_ms: int = 0
    last_event_ts: str | None = None

    def phase_elapsed_sec(self) -> float:
        if self.phase_started_at:
            return round(time.monotonic() - self.phase_started_at, 1)
        return 0.0

    def cycle_elapsed_sec(self) -> float:
        if self.cycle_started_at:
            return round(time.monotonic() - self.cycle_started_at, 1)
        return 0.0

    def to_dict(self) -> dict:
        return {
            "engine_status": self.engine_status,
            "run_id": self.run_id,
            "phase": self.phase,
            "phase_detail": self.phase_detail,
            "phase_elapsed_sec": self.phase_elapsed_sec(),
            "cycle_elapsed_sec": self.cycle_elapsed_sec(),
            "next_cycle_at": self.next_cycle_at,
            "counters": {
                "sources_ok": self.counters.sources_ok,
                "sources_failed": self.counters.sources_failed,
                "items_found": self.counters.items_found,
                "items_new": self.counters.items_new,
                "stories_new": self.counters.stories_new,
                "stories_updated": self.counters.stories_updated,
                "published_web": self.counters.published_web,
                "published_fb": self.counters.published_fb,
                "errors_total": self.counters.errors_total,
            },
            "last_run_status": self.last_run_status,
            "last_run_elapsed_ms": self.last_run_elapsed_ms,
            "last_event_ts": self.last_event_ts,
        }


# ── EventBus ──────────────────────────────────────────────────────────────────


class EventBus:
    """Asyncio-native event bus.  emit() is a coroutine; call with await."""

    MAX_HISTORY = 200       # events retained for late-joining clients
    MAX_SUBSCRIBERS = 20    # max concurrent SSE streams

    def __init__(self) -> None:
        self.state = RunState()
        self._subscribers: list[asyncio.Queue[Event | None]] = []
        self._history: list[Event] = []

    # ── Public API ────────────────────────────────────────────────────────────

    async def emit(self, type: str, data: dict, phase: str | None = None) -> None:
        """Emit an event: update state, append to history, broadcast to all SSE clients."""
        ev = Event(type=type, data=data, phase=phase)
        self._update_state(ev)
        self._history.append(ev)
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def subscribe(self, replay_history: bool = True) -> AsyncIterator[Event]:
        """Async generator: yields events as they arrive.

        Yields recent history first (so a connecting client catches up),
        then live events.  Stops when the caller disconnects (GeneratorExit).
        """
        if len(self._subscribers) >= self.MAX_SUBSCRIBERS:
            return

        q: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        try:
            if replay_history:
                for ev in self._history[-200:]:  # full history on connect
                    yield ev
            while True:
                ev = await q.get()
                if ev is None:
                    break
                yield ev
        except asyncio.CancelledError:
            pass
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def unsubscribe_all(self) -> None:
        """Signal all active SSE streams to close (e.g. on shutdown)."""
        for q in self._subscribers:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # ── State updater ─────────────────────────────────────────────────────────

    def _update_state(self, ev: Event) -> None:
        s = self.state
        s.last_event_ts = ev.ts
        t = ev.type
        d = ev.data

        if t == "engine_start":
            s.engine_status = "running"
        elif t == "engine_stop":
            s.engine_status = "idle"
            s.run_id = None
            s.phase = None
            s.phase_detail = None

        elif t == "cycle_start":
            s.engine_status = "running"
            s.run_id = d.get("run_id")
            s.cycle_started_at = time.monotonic()
            s.phase = None
            s.phase_detail = None
            s.counters = RunCountersSnapshot()

        elif t == "cycle_done":
            s.engine_status = "idle"
            s.phase = None
            s.phase_detail = None
            s.last_run_status = d.get("status")
            s.last_run_elapsed_ms = d.get("elapsed_ms", 0)
            # copy final counters
            c = d.get("counters", {})
            s.counters = RunCountersSnapshot(
                sources_ok=c.get("sources_ok", 0),
                sources_failed=c.get("sources_failed", 0),
                items_found=c.get("items_found", 0),
                items_new=c.get("items_new", 0),
                stories_new=c.get("stories_new", 0),
                stories_updated=c.get("stories_updated", 0),
                published_web=c.get("published_web", 0),
                published_fb=c.get("published_fb", 0),
                errors_total=c.get("errors_total", 0),
            )

        elif t == "phase_start":
            s.phase = ev.phase
            s.phase_started_at = time.monotonic()
            s.phase_detail = None

        elif t == "phase_done":
            s.phase_detail = None

        elif t == "source_ok":
            s.phase_detail = d.get("source")
            s.counters.sources_ok += 1
            s.counters.items_found += d.get("found", 0)
            s.counters.items_new += d.get("new", 0)
            s.counters.stories_new += d.get("stories_new", 0)
            s.counters.stories_updated += d.get("stories_updated", 0)

        elif t == "source_fail":
            s.phase_detail = d.get("source")
            s.counters.sources_failed += 1
            s.counters.errors_total += 1

        elif t == "story_processing":
            idx = d.get("idx", 0)
            total = d.get("total", 0)
            s.phase_detail = f"story {idx}/{total}"

        elif t == "story_ok":
            s.counters.published_web += 1

        elif t == "story_fail":
            s.counters.errors_total += 1

        elif t == "fb_posted":
            s.counters.published_fb += 1

        elif t == "fb_fail":
            s.counters.errors_total += 1

        elif t == "sleeping":
            s.engine_status = "sleeping"
            s.phase = None
            s.phase_detail = None
            s.run_id = None
            s.next_cycle_at = d.get("next_cycle_at")

        elif t == "cycle_starting":
            s.engine_status = "running"
            s.next_cycle_at = None


# ── Global singleton ──────────────────────────────────────────────────────────

BUS: EventBus = EventBus()
