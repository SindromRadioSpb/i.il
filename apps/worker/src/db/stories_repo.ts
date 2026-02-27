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
