import { getSourceById } from '../sources/registry';

interface StoryRow {
  story_id: string;
  start_at: string;
  last_update_at: string;
  title_ru: string | null;
  summary_ru: string | null;
  category: string;
  risk_level: string;
  state: string;
}

interface TimelineRow {
  item_id: string;
  source_id: string;
  title_he: string;
  url: string;
  published_at: string | null;
  updated_at: string | null;
}

export interface StoryDetail {
  story_id: string;
  canonical_url: string;
  title_ru: string | null;
  summary_ru: string | null;
  category: string;
  risk_level: string;
  start_at: string;
  last_update_at: string;
  sources: { source_id: string; name: string; url: string }[];
  timeline: TimelineRow[];
}

/**
 * Fetch full story detail including timeline items and contributing sources.
 * Returns null when the story does not exist.
 */
export async function getStory(
  db: D1Database,
  storyId: string,
): Promise<StoryDetail | null> {
  const row = await db
    .prepare(
      `SELECT story_id, start_at, last_update_at, title_ru, summary_ru,
              category, risk_level, state
       FROM stories
       WHERE story_id = ?`,
    )
    .bind(storyId)
    .first<StoryRow>();

  if (!row) return null;

  const timeline = (
    await db
      .prepare(
        `SELECT i.item_id, i.source_id, i.title_he,
                i.source_url AS url, i.published_at, i.updated_at
         FROM story_items si
         JOIN items i ON i.item_id = si.item_id
         WHERE si.story_id = ?
         ORDER BY COALESCE(i.published_at, si.added_at) DESC
         LIMIT 50`,
      )
      .bind(storyId)
      .all<TimelineRow>()
  ).results;

  // Deduplicate contributing source IDs and enrich from registry
  const seenSourceIds = new Set<string>();
  for (const item of timeline) seenSourceIds.add(item.source_id);

  const sources = [...seenSourceIds]
    .map(id => {
      const src = getSourceById(id);
      return src !== undefined ? { source_id: id, name: src.name, url: src.url } : null;
    })
    .filter((s): s is NonNullable<typeof s> => s !== null);

  return {
    story_id: row.story_id,
    canonical_url: `/story/${row.story_id}`,
    title_ru: row.title_ru,
    summary_ru: row.summary_ru,
    category: row.category,
    risk_level: row.risk_level,
    start_at: row.start_at,
    last_update_at: row.last_update_at,
    sources,
    timeline,
  };
}
