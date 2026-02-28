"""observe/report.py — Generate daily markdown summary report.

Aggregates metrics, story counts, FB posts, and errors for a given date
(UTC) and writes a human-readable markdown report into daily_reports.

Usage:
    from observe.report import generate_daily_report
    md = await generate_daily_report(db, "2026-02-28")
"""

from __future__ import annotations

from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def _count_stories_published(db, date: str) -> int:
    """Stories that transitioned to 'published' on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT COUNT(*) AS n FROM stories
        WHERE state = 'published'
          AND last_update_at >= ? AND last_update_at <= ?
        """,
        (start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"])


async def _count_fb_posts(db, date: str) -> int:
    """FB publications created on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT COUNT(*) AS n FROM publications
        WHERE fb_posted_at >= ? AND fb_posted_at <= ?
        """,
        (start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"])


async def _count_errors(db, date: str) -> int:
    """Total error_events recorded on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT COUNT(*) AS n FROM error_events
        WHERE created_at >= ? AND created_at <= ?
        """,
        (start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"])


async def _count_items_ingested(db, date: str) -> int:
    """New items ingested on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT COUNT(*) AS n FROM items
        WHERE ingested_at >= ? AND ingested_at <= ?
        """,
        (start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"])


async def _get_daily_metrics(db, date: str) -> dict[str, dict[str, float]]:
    """Return metric sums for all runs on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT phase, key, SUM(value) AS total
        FROM metrics
        WHERE recorded_at >= ? AND recorded_at <= ?
        GROUP BY phase, key
        ORDER BY phase, key
        """,
        (start, end),
    ) as cur:
        rows = await cur.fetchall()

    result: dict[str, dict[str, float]] = {}
    for row in rows:
        result.setdefault(row["phase"], {})[row["key"]] = float(row["total"])
    return result


async def _get_run_count(db, date: str) -> int:
    """Number of completed scheduler runs on the given UTC date."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT COUNT(*) AS n FROM runs
        WHERE started_at >= ? AND started_at <= ?
          AND finished_at IS NOT NULL
        """,
        (start, end),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"])


async def _get_top_errors(db, date: str, limit: int = 5) -> list[dict]:
    """Top error events for the date, newest first."""
    start = f"{date}T00:00:00.000Z"
    end = f"{date}T23:59:59.999Z"
    async with db.execute(
        """
        SELECT phase, code, message, created_at
        FROM error_events
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (start, end, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


def _fmt_metric(metrics: dict[str, dict[str, float]], phase: str, key: str) -> str:
    val = metrics.get(phase, {}).get(key)
    if val is None:
        return "—"
    if val == int(val):
        return str(int(val))
    return f"{val:.1f}"


async def generate_daily_report(db, date: str) -> str:
    """Generate a markdown daily report for the given UTC date (YYYY-MM-DD).

    Saves the report to daily_reports and returns the markdown string.
    """
    stories_published = await _count_stories_published(db, date)
    fb_posts = await _count_fb_posts(db, date)
    errors_total = await _count_errors(db, date)
    items_ingested = await _count_items_ingested(db, date)
    run_count = await _get_run_count(db, date)
    metrics = await _get_daily_metrics(db, date)
    top_errors = await _get_top_errors(db, date)

    # Build markdown
    lines: list[str] = [
        f"# Daily Report — {date}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Scheduler runs | {run_count} |",
        f"| Items ingested | {items_ingested} |",
        f"| Stories published | {stories_published} |",
        f"| FB posts | {fb_posts} |",
        f"| Errors | {errors_total} |",
        "",
        "## Metrics by Phase",
        "",
    ]

    phase_order = ["ingest", "cluster", "summary", "images", "fb", "sync"]
    shown_phases = set()
    for phase in phase_order:
        if phase in metrics:
            shown_phases.add(phase)
            lines.append(f"### {phase.capitalize()}")
            lines.append("")
            lines.append("| Key | Value |")
            lines.append("|-----|-------|")
            for key, val in sorted(metrics[phase].items()):
                display = str(int(val)) if val == int(val) else f"{val:.1f}"
                lines.append(f"| {key} | {display} |")
            lines.append("")

    # Any phases not in the order list
    for phase in sorted(metrics.keys()):
        if phase not in shown_phases:
            lines.append(f"### {phase.capitalize()}")
            lines.append("")
            lines.append("| Key | Value |")
            lines.append("|-----|-------|")
            for key, val in sorted(metrics[phase].items()):
                display = str(int(val)) if val == int(val) else f"{val:.1f}"
                lines.append(f"| {key} | {display} |")
            lines.append("")

    if top_errors:
        lines.append("## Recent Errors (last 5)")
        lines.append("")
        for e in top_errors:
            lines.append(
                f"- `{e['created_at']}` **{e['phase']}** / {e['code']}: {e['message']}"
            )
        lines.append("")
    else:
        lines.append("## Errors")
        lines.append("")
        lines.append("No errors recorded.")
        lines.append("")

    lines.append(f"*Generated at {_now_iso()}*")

    report_md = "\n".join(lines)

    # Upsert into daily_reports
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO daily_reports
          (report_date, report_markdown, stories_published, fb_posts,
           errors_total, generated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
          report_markdown   = excluded.report_markdown,
          stories_published = excluded.stories_published,
          fb_posts          = excluded.fb_posts,
          errors_total      = excluded.errors_total,
          generated_at      = excluded.generated_at
        """,
        (date, report_md, stories_published, fb_posts, errors_total, now),
    )
    await db.commit()

    return report_md
