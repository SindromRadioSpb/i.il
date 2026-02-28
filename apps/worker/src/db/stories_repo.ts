export interface StoryCandidate {
  storyId: string;
  lastUpdateAt: string;
  titleHe: string; // founding item's title_he — used for clustering
}

/**
 * Fetch stories updated within the given time window, each paired with the
 * title_he of their first-added item (used as the clustering anchor).
 *
 * Uses a correlated subquery to get the founding item per story — valid SQLite.
 */
export async function findRecentStories(
  db: D1Database,
  windowMs: number,
): Promise<StoryCandidate[]> {
  const since = new Date(Date.now() - windowMs).toISOString();

  const result = await db
    .prepare(
      `SELECT s.story_id     AS storyId,
              s.last_update_at AS lastUpdateAt,
              i.title_he       AS titleHe
       FROM stories s
       JOIN story_items si ON si.story_id = s.story_id
         AND si.added_at = (
           SELECT MIN(si2.added_at) FROM story_items si2
           WHERE si2.story_id = s.story_id
         )
       JOIN items i ON i.item_id = si.item_id
       WHERE s.last_update_at >= ?
         AND s.state != 'hidden'
       ORDER BY s.last_update_at DESC
       LIMIT 100`,
    )
    .bind(since)
    .all<StoryCandidate>();

  return result.results;
}

/** Insert a new story row in state=draft. */
export async function createStory(
  db: D1Database,
  storyId: string,
  startAt: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO stories
         (story_id, start_at, last_update_at, category, risk_level, state)
       VALUES (?, ?, ?, 'other', 'low', 'draft')`,
    )
    .bind(storyId, startAt, startAt)
    .run();
}

// ---------------------------------------------------------------------------
// Summary pipeline helpers
// ---------------------------------------------------------------------------

export interface StoryForSummary {
  storyId: string;
  riskLevel: string;
  summaryHash: string | null;
}

export interface StoryItemForSummary {
  itemId: string;
  titleHe: string;
  sourceId: string;
  publishedAt: string | null;
}

/** Fetch draft stories that need a Russian summary generated.
 *  Excludes stories with editorial_hold = 1 — those wait for manual release. */
export async function getStoriesNeedingSummary(
  db: D1Database,
  limit: number,
): Promise<StoryForSummary[]> {
  const result = await db
    .prepare(
      `SELECT story_id     AS storyId,
              risk_level   AS riskLevel,
              summary_hash AS summaryHash
       FROM stories
       WHERE state = 'draft'
         AND editorial_hold = 0
       ORDER BY last_update_at DESC
       LIMIT ?`,
    )
    .bind(limit)
    .all<StoryForSummary>();
  return result.results;
}

/** Fetch the items belonging to a story, most-recent first (max 10). */
export async function getStoryItemsForSummary(
  db: D1Database,
  storyId: string,
): Promise<StoryItemForSummary[]> {
  const result = await db
    .prepare(
      `SELECT i.item_id    AS itemId,
              i.title_he   AS titleHe,
              i.source_id  AS sourceId,
              i.published_at AS publishedAt
       FROM story_items si
       JOIN items i ON i.item_id = si.item_id
       WHERE si.story_id = ?
       ORDER BY COALESCE(i.published_at, si.added_at) DESC
       LIMIT 10`,
    )
    .bind(storyId)
    .all<StoryItemForSummary>();
  return result.results;
}

/**
 * Persist the generated summary: update the story (state → published) and
 * create/update the corresponding publications row in a single batch.
 */
export async function updateStorySummary(
  db: D1Database,
  storyId: string,
  titleRu: string,
  summaryRu: string,
  summaryHash: string,
  riskLevel: string,
): Promise<void> {
  const now = new Date().toISOString();
  await db.batch([
    db
      .prepare(
        `UPDATE stories
         SET title_ru        = ?,
             summary_ru      = ?,
             summary_hash    = ?,
             summary_version = summary_version + 1,
             risk_level      = ?,
             state           = 'published'
         WHERE story_id = ?`,
      )
      .bind(titleRu, summaryRu, summaryHash, riskLevel, storyId),
    db
      .prepare(
        `INSERT OR IGNORE INTO publications (story_id, web_status, fb_status)
         VALUES (?, 'pending', 'disabled')`,
      )
      .bind(storyId),
    db
      .prepare(
        `UPDATE publications
         SET web_status = 'published', web_published_at = ?
         WHERE story_id = ?`,
      )
      .bind(now, storyId),
  ]);
}

// ---------------------------------------------------------------------------

/** Bump last_update_at for a story that gained a new item. */
export async function updateStoryLastUpdate(
  db: D1Database,
  storyId: string,
  lastUpdateAt: string,
): Promise<void> {
  await db
    .prepare(`UPDATE stories SET last_update_at = ? WHERE story_id = ?`)
    .bind(lastUpdateAt, storyId)
    .run();
}
