"""observe/why_not.py — Diagnostic: why hasn't a story been published?

Returns a human-readable list of reasons for each gate that hasn't been
cleared, so operators can quickly understand why a story is stuck.

Usage:
    from observe.why_not import why_not_published
    reasons = await why_not_published(db, "story-id-abc")
    for r in reasons: print(r)
"""

from __future__ import annotations


async def why_not_published(db, story_id: str) -> list[str]:
    """Return a list of reasons why story_id has not been published.

    An empty list means all gates are satisfied and the story should
    appear in the CF feed (or already does).

    Checks (in order):
    1. Story exists
    2. State = published
    3. editorial_hold = 0
    4. summary_ru is not null
    5. title_ru is not null
    6. Has at least one item attached
    7. cf_synced_at is not null (synced to CF)
    8. Has a publication record
    """
    async with db.execute(
        """
        SELECT story_id, state, editorial_hold, title_ru, summary_ru,
               cf_synced_at
        FROM stories WHERE story_id = ?
        """,
        (story_id,),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return [f"Story '{story_id}' not found in database"]

    reasons: list[str] = []

    if row["state"] != "published":
        reasons.append(f"state={row['state']!r} (must be 'published')")

    if row["editorial_hold"]:
        reasons.append("editorial_hold=1 — story is on hold; use /release to resume")

    if not row["summary_ru"]:
        reasons.append("summary_ru is NULL — AI summary not yet generated")

    if not row["title_ru"]:
        reasons.append("title_ru is NULL — title not extracted from summary")

    # Item count
    async with db.execute(
        "SELECT COUNT(*) AS n FROM story_items WHERE story_id = ?",
        (story_id,),
    ) as cur:
        item_row = await cur.fetchone()
    if item_row["n"] == 0:
        reasons.append("no items attached to story — clustering may not have run yet")

    if not row["cf_synced_at"]:
        reasons.append(
            "cf_synced_at is NULL — story has not been pushed to Cloudflare yet"
        )

    # Publication record
    async with db.execute(
        "SELECT COUNT(*) AS n FROM publications WHERE story_id = ?",
        (story_id,),
    ) as cur:
        pub_row = await cur.fetchone()
    if pub_row["n"] == 0:
        reasons.append("no publication record — FB post not yet created")

    return reasons
