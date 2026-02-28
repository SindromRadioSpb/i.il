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
