import { encodeCursor, decodeCursor } from './cursor';

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;

interface StoryRow {
  story_id: string;
  start_at: string;
  last_update_at: string;
  title_ru: string | null;
  summary_ru: string | null;
  category: string;
  risk_level: string;
  source_count: number;
}

const FEED_SQL_NO_CURSOR = `
  SELECT s.story_id, s.start_at, s.last_update_at, s.title_ru, s.summary_ru,
         s.category, s.risk_level,
         (SELECT COUNT(DISTINCT i2.source_id)
          FROM story_items si2 JOIN items i2 ON i2.item_id = si2.item_id
          WHERE si2.story_id = s.story_id) AS source_count
  FROM stories s
  WHERE s.state != 'hidden'
  ORDER BY s.last_update_at DESC, s.story_id DESC
  LIMIT ?`;

const FEED_SQL_WITH_CURSOR = `
  SELECT s.story_id, s.start_at, s.last_update_at, s.title_ru, s.summary_ru,
         s.category, s.risk_level,
         (SELECT COUNT(DISTINCT i2.source_id)
          FROM story_items si2 JOIN items i2 ON i2.item_id = si2.item_id
          WHERE si2.story_id = s.story_id) AS source_count
  FROM stories s
  WHERE s.state != 'hidden'
    AND (s.last_update_at < ? OR (s.last_update_at = ? AND s.story_id < ?))
  ORDER BY s.last_update_at DESC, s.story_id DESC
  LIMIT ?`;

export type FeedError = {
  type: 'invalid_request';
  message: string;
  details: Record<string, unknown>;
};

export interface FeedResult {
  stories: {
    story_id: string;
    canonical_url: string;
    title_ru: string | null;
    summary_excerpt_ru: string | null;
    category: string;
    risk_level: string;
    source_count: number;
    start_at: string;
    last_update_at: string;
  }[];
  next_cursor: string | null;
}

export async function getFeed(
  db: D1Database,
  limitParam: string | null,
  cursorParam: string | null,
): Promise<FeedResult | FeedError> {
  // Validate limit
  const rawLimit = limitParam !== null ? parseInt(limitParam, 10) : DEFAULT_LIMIT;
  if (!Number.isInteger(rawLimit) || rawLimit < 1 || rawLimit > MAX_LIMIT) {
    return {
      type: 'invalid_request',
      message: 'Invalid limit parameter',
      details: { param: 'limit', value: limitParam, max: MAX_LIMIT },
    };
  }

  // Decode cursor
  let cursor: { last_update_at: string; story_id: string } | null = null;
  if (cursorParam !== null) {
    cursor = decodeCursor(cursorParam);
    if (cursor === null) {
      return {
        type: 'invalid_request',
        message: 'Invalid cursor',
        details: { param: 'cursor' },
      };
    }
  }

  // Fetch limit+1 rows to detect next page
  const fetchLimit = rawLimit + 1;
  let rows: StoryRow[];

  if (cursor === null) {
    rows = (await db.prepare(FEED_SQL_NO_CURSOR).bind(fetchLimit).all<StoryRow>())
      .results;
  } else {
    rows = (
      await db
        .prepare(FEED_SQL_WITH_CURSOR)
        .bind(cursor.last_update_at, cursor.last_update_at, cursor.story_id, fetchLimit)
        .all<StoryRow>()
    ).results;
  }

  // Determine next_cursor
  let next_cursor: string | null = null;
  if (rows.length > rawLimit) {
    rows = rows.slice(0, rawLimit);
    const last = rows[rows.length - 1]!;
    next_cursor = encodeCursor(last.last_update_at, last.story_id);
  }

  const stories = rows.map(r => ({
    story_id: r.story_id,
    canonical_url: `/story/${r.story_id}`,
    title_ru: r.title_ru,
    summary_excerpt_ru:
      r.summary_ru !== null ? r.summary_ru.slice(0, 250) : null,
    category: r.category,
    risk_level: r.risk_level,
    source_count: r.source_count,
    start_at: r.start_at,
    last_update_at: r.last_update_at,
  }));

  return { stories, next_cursor };
}
