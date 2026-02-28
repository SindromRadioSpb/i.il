import type { D1Database } from '@cloudflare/workers-types';

export interface FbStoryRow {
  storyId: string;
  titleRu: string | null;
  summaryRu: string | null;
}

/**
 * Fetch published stories eligible for Facebook posting.
 *
 * Eligibility rules:
 *  - web_status = 'published' (story visible on site)
 *  - fb_status IN ('disabled', 'failed')  — 'disabled' = never attempted,
 *    'failed' = transient error → auto-retry; auth_error / rate_limited are
 *    NOT retried automatically (need manual reset after fixing credentials)
 *  - fb_attempts < 5  — permanent skip after 5 consecutive failures
 *  - fb_post_id IS NULL  — idempotency guard: if the FB API call succeeded but
 *    the DB write crashed, the post_id would already be set; skip to avoid
 *    double-posting
 */
export async function getStoriesForFbPosting(
  db: D1Database,
  limit: number,
): Promise<FbStoryRow[]> {
  const result = await db
    .prepare(
      `SELECT p.story_id, s.title_ru, s.summary_ru
       FROM publications p
       JOIN stories s USING(story_id)
       WHERE p.web_status = 'published'
         AND p.fb_status IN ('disabled', 'failed')
         AND p.fb_attempts < 5
         AND p.fb_post_id IS NULL
         AND s.title_ru IS NOT NULL
         AND s.summary_ru IS NOT NULL
       ORDER BY s.last_update_at DESC
       LIMIT ?`,
    )
    .bind(limit)
    .all<{ story_id: string; title_ru: string | null; summary_ru: string | null }>();

  return (result.results ?? []).map(r => ({
    storyId: r.story_id,
    titleRu: r.title_ru,
    summaryRu: r.summary_ru,
  }));
}

/** Mark a story as successfully posted to Facebook. */
export async function markFbPosted(
  db: D1Database,
  storyId: string,
  postId: string,
): Promise<void> {
  const now = new Date().toISOString();
  await db
    .prepare(
      `UPDATE publications
       SET fb_status = 'posted', fb_post_id = ?, fb_posted_at = ?
       WHERE story_id = ?`,
    )
    .bind(postId, now, storyId)
    .run();
}

/**
 * Mark a Facebook posting attempt as failed.
 * @param status - One of: 'failed' | 'auth_error' | 'rate_limited'
 */
export async function markFbFailed(
  db: D1Database,
  storyId: string,
  status: 'failed' | 'auth_error' | 'rate_limited',
  errorMsg: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE publications
       SET fb_status = ?, fb_error_last = ?, fb_attempts = fb_attempts + 1
       WHERE story_id = ?`,
    )
    .bind(status, errorMsg, storyId)
    .run();
}
