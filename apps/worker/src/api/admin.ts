import type { RunRow } from './health';

export interface ErrorRow {
  event_id: string;
  run_id: string;
  phase: string;
  source_id: string | null;
  story_id: string | null;
  code: string | null;
  message: string | null;
  created_at: string;
}

export interface DraftStoryRow {
  story_id: string;
  start_at: string;
  last_update_at: string;
  editorial_hold: number; // 0 | 1
  item_count: number;
  title_sample: string | null; // title_he of the founding item
}

/**
 * Fetch the most recent N cron run records, newest first.
 * Returns an empty array on any DB error.
 */
export async function getRecentRuns(db: D1Database, limit = 20): Promise<RunRow[]> {
  try {
    const result = await db
      .prepare(
        `SELECT run_id, started_at, finished_at, status,
                sources_ok, sources_failed, items_found, items_new,
                stories_new, stories_updated, published_web, published_fb,
                errors_total, duration_ms
         FROM runs
         ORDER BY started_at DESC
         LIMIT ?`,
      )
      .bind(limit)
      .all<RunRow>();
    return result.results ?? [];
  } catch {
    return [];
  }
}

/**
 * Fetch all error events for a specific run, ordered by creation time.
 * Returns an empty array on any DB error.
 */
export async function getRunErrors(db: D1Database, runId: string): Promise<ErrorRow[]> {
  try {
    const result = await db
      .prepare(
        `SELECT event_id, run_id, phase, source_id, story_id, code, message, created_at
         FROM error_events
         WHERE run_id = ?
         ORDER BY created_at`,
      )
      .bind(runId)
      .all<ErrorRow>();
    return result.results ?? [];
  } catch {
    return [];
  }
}

export interface DraftCounts {
  total: number;
  held: number;
  pending: number; // total - held
}

/** Real-time counts of draft stories by hold status. */
export async function getDraftCounts(db: D1Database): Promise<DraftCounts> {
  try {
    const result = await db
      .prepare(
        `SELECT COUNT(*) AS total,
                SUM(editorial_hold) AS held,
                SUM(CASE WHEN editorial_hold = 0 THEN 1 ELSE 0 END) AS pending
         FROM stories
         WHERE state = 'draft'`,
      )
      .all<{ total: number; held: number | null; pending: number | null }>();
    const row = result.results[0];
    if (!row) return { total: 0, held: 0, pending: 0 };
    return { total: row.total ?? 0, held: row.held ?? 0, pending: row.pending ?? 0 };
  } catch {
    return { total: 0, held: 0, pending: 0 };
  }
}

/**
 * Fetch draft stories for editorial review, newest first.
 * Includes the founding item's Hebrew title as a preview.
 */
export async function getDraftStories(db: D1Database, limit = 50): Promise<DraftStoryRow[]> {
  try {
    const result = await db
      .prepare(
        `SELECT s.story_id,
                s.start_at,
                s.last_update_at,
                s.editorial_hold,
                COUNT(si.item_id) AS item_count,
                (SELECT i.title_he
                 FROM story_items si2
                 JOIN items i ON i.item_id = si2.item_id
                 WHERE si2.story_id = s.story_id
                 ORDER BY si2.added_at ASC LIMIT 1) AS title_sample
         FROM stories s
         LEFT JOIN story_items si ON si.story_id = s.story_id
         WHERE s.state = 'draft'
         GROUP BY s.story_id
         ORDER BY s.last_update_at DESC
         LIMIT ?`,
      )
      .bind(limit)
      .all<DraftStoryRow>();
    return result.results ?? [];
  } catch {
    return [];
  }
}

/**
 * Set editorial_hold = 1 on a draft story.
 * Returns true if a row was updated (story existed and was in draft state).
 */
export async function holdStory(db: D1Database, storyId: string): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE stories
       SET editorial_hold = 1
       WHERE story_id = ? AND state = 'draft'`,
    )
    .bind(storyId)
    .run();
  return ((result.meta as { changes?: number }).changes ?? 0) > 0;
}

/**
 * Set editorial_hold = 0 on a story, allowing the summary pipeline to pick it up.
 * Returns true if a row was updated (story existed).
 */
export async function releaseStory(db: D1Database, storyId: string): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE stories
       SET editorial_hold = 0
       WHERE story_id = ?`,
    )
    .bind(storyId)
    .run();
  return ((result.meta as { changes?: number }).changes ?? 0) > 0;
}

/**
 * Delete a single story by ID.
 * CASCADE removes story_items and publications automatically.
 * Returns true if a row was deleted.
 */
export async function deleteStory(db: D1Database, storyId: string): Promise<boolean> {
  const result = await db
    .prepare(`DELETE FROM stories WHERE story_id = ?`)
    .bind(storyId)
    .run();
  return ((result.meta as { changes?: number }).changes ?? 0) > 0;
}

/**
 * Delete ALL stories in draft state.
 * Returns the number of deleted rows.
 */
export async function deleteAllDrafts(db: D1Database): Promise<number> {
  const result = await db
    .prepare(`DELETE FROM stories WHERE state = 'draft'`)
    .run();
  return (result.meta as { changes?: number }).changes ?? 0;
}

/**
 * Set state = 'hidden' on a published story, removing it from the public feed.
 * Returns true if a row was updated.
 */
export async function hideStory(db: D1Database, storyId: string): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE stories
       SET state = 'hidden'
       WHERE story_id = ? AND state = 'published'`,
    )
    .bind(storyId)
    .run();
  return ((result.meta as { changes?: number }).changes ?? 0) > 0;
}

/**
 * Reset Facebook publication status so the story will be retried.
 * Sets fb_status = 'pending', clears fb_attempts, fb_error_last, fb_post_id.
 * Returns true if a publications row was updated.
 */
export async function resetFbStatus(db: D1Database, storyId: string): Promise<boolean> {
  const result = await db
    .prepare(
      `UPDATE publications
       SET fb_status = 'pending',
           fb_attempts = 0,
           fb_error_last = NULL,
           fb_post_id = NULL,
           fb_posted_at = NULL
       WHERE story_id = ?`,
    )
    .bind(storyId)
    .run();
  return ((result.meta as { changes?: number }).changes ?? 0) > 0;
}

/**
 * Purge run records (+ cascading error_events) older than `days` days.
 * Returns the number of deleted run rows.
 */
export async function purgeOldRuns(db: D1Database, days: number): Promise<number> {
  const cutoff = new Date(Date.now() - days * 86_400_000).toISOString();
  const result = await db
    .prepare(`DELETE FROM runs WHERE started_at < ?`)
    .bind(cutoff)
    .run();
  return (result.meta as { changes?: number }).changes ?? 0;
}

/**
 * Purge error_events older than `days` days.
 * Returns the number of deleted rows.
 */
export async function purgeOldErrors(db: D1Database, days: number): Promise<number> {
  const cutoff = new Date(Date.now() - days * 86_400_000).toISOString();
  const result = await db
    .prepare(`DELETE FROM error_events WHERE created_at < ?`)
    .bind(cutoff)
    .run();
  return (result.meta as { changes?: number }).changes ?? 0;
}

/**
 * Fetch published stories for admin review (newest first).
 */
export interface PublishedStoryRow {
  story_id: string;
  last_update_at: string;
  title_ru: string | null;
  category: string;
  fb_status: string | null;
  fb_post_id: string | null;
  fb_attempts: number;
}

export async function getPublishedStories(db: D1Database, limit = 30): Promise<PublishedStoryRow[]> {
  try {
    const result = await db
      .prepare(
        `SELECT s.story_id, s.last_update_at, s.title_ru, s.category,
                p.fb_status, p.fb_post_id, p.fb_attempts
         FROM stories s
         LEFT JOIN publications p ON p.story_id = s.story_id
         WHERE s.state = 'published'
         ORDER BY s.last_update_at DESC
         LIMIT ?`,
      )
      .bind(limit)
      .all<PublishedStoryRow>();
    return result.results ?? [];
  } catch {
    return [];
  }
}
