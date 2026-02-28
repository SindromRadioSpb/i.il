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
