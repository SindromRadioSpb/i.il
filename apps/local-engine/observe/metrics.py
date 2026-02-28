"""observe/metrics.py — Per-run metrics recorder backed by the metrics table.

Usage:
    from observe.metrics import MetricsRecorder
    rec = MetricsRecorder(run_id="abc123")
    await rec.record(db, "ingest", "items_new", 42)
    summary = await rec.get_summary(db, hours=24)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class MetricsRecorder:
    """Records and queries run-level metrics in the metrics table."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id

    async def record(
        self,
        db,
        phase: str,
        key: str,
        value: float,
        *,
        run_id: str | None = None,
    ) -> None:
        """Insert a single metric row.

        Args:
            db:     aiosqlite connection.
            phase:  Component phase, e.g. "ingest", "cluster", "summary".
            key:    Metric name, e.g. "items_new", "duration_ms".
            value:  Numeric value (REAL).
            run_id: Override instance run_id for this recording.
        """
        rid = run_id or self.run_id
        await db.execute(
            """
            INSERT INTO metrics (run_id, phase, key, value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rid, phase, key, value, _now_iso()),
        )
        await db.commit()

    async def get_summary(
        self,
        db,
        *,
        hours: int = 24,
    ) -> dict[str, dict[str, float]]:
        """Return aggregate metric sums grouped by phase.key over the last N hours.

        Returns:
            Nested dict:  { "ingest": { "items_new": 42.0, ... }, ... }
        """
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        async with db.execute(
            """
            SELECT phase, key, SUM(value) AS total
            FROM metrics
            WHERE recorded_at >= ?
            GROUP BY phase, key
            ORDER BY phase, key
            """,
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

        result: dict[str, dict[str, float]] = {}
        for row in rows:
            phase = row["phase"]
            key = row["key"]
            total = float(row["total"])
            result.setdefault(phase, {})[key] = total
        return result

    async def get_run_metrics(
        self,
        db,
        run_id: str,
    ) -> dict[str, dict[str, float]]:
        """Return all metrics for a specific run_id grouped by phase.key."""
        async with db.execute(
            """
            SELECT phase, key, SUM(value) AS total
            FROM metrics
            WHERE run_id = ?
            GROUP BY phase, key
            ORDER BY phase, key
            """,
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()

        result: dict[str, dict[str, float]] = {}
        for row in rows:
            result.setdefault(row["phase"], {})[row["key"]] = float(row["total"])
        return result
