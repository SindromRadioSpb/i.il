/**
 * api/sync.ts — POST /api/v1/sync/stories
 *
 * Receives published stories from the local Python engine and upserts them
 * into D1 so the Cloudflare Pages site stays current.
 *
 * Auth: Authorization: Bearer <CF_SYNC_TOKEN>
 * Body: { stories: SyncStory[] }
 * Response: { ok: true, synced: N }
 */

import type { Env } from '../index';

interface SyncItem {
  item_id: string;
  source_id: string;
  source_url: string;
  normalized_url: string;
  item_key: string;
  title_he: string;
  published_at: string | null;
  date_confidence: string;
  ingested_at: string;
}

interface SyncStory {
  story_id: string;
  start_at: string;
  last_update_at: string;
  title_ru: string | null;
  summary_ru: string | null;
  category: string;
  risk_level: string;
  state: string;
  summary_version?: number;
  hashtags?: string | null;
  items?: SyncItem[];
}

interface SyncPayload {
  stories: SyncStory[];
}

function jsonResp(data: unknown, status = 200): Response {
  return Response.json(data, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

export async function handleSync(request: Request, env: Env): Promise<Response> {
  // Require CF_SYNC_TOKEN to be configured
  if (!env.CF_SYNC_TOKEN) {
    return jsonResp(
      { ok: false, error: { code: 'sync_disabled', message: 'CF_SYNC_TOKEN is not configured' } },
      403,
    );
  }

  // Validate Authorization header
  const authHeader = request.headers.get('authorization') ?? '';
  if (authHeader !== `Bearer ${env.CF_SYNC_TOKEN}`) {
    return jsonResp(
      { ok: false, error: { code: 'unauthorized', message: 'Invalid or missing Authorization header' } },
      401,
    );
  }

  // Parse body
  let payload: SyncPayload;
  try {
    payload = (await request.json()) as SyncPayload;
  } catch {
    return jsonResp(
      { ok: false, error: { code: 'invalid_json', message: 'Request body must be valid JSON' } },
      400,
    );
  }

  if (!Array.isArray(payload?.stories)) {
    return jsonResp(
      { ok: false, error: { code: 'invalid_request', message: '"stories" must be an array' } },
      400,
    );
  }

  // Upsert each story via D1 batch
  let synced = 0;

  for (const story of payload.stories) {
    const stmts: D1PreparedStatement[] = [];

    // Upsert story row
    stmts.push(
      env.DB.prepare(`
        INSERT INTO stories (
          story_id, start_at, last_update_at, title_ru, summary_ru,
          summary_version, category, risk_level, state, hashtags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(story_id) DO UPDATE SET
          title_ru        = excluded.title_ru,
          summary_ru      = excluded.summary_ru,
          summary_version = excluded.summary_version,
          category        = excluded.category,
          risk_level      = excluded.risk_level,
          state           = excluded.state,
          hashtags        = excluded.hashtags,
          last_update_at  = excluded.last_update_at
      `).bind(
        story.story_id,
        story.start_at,
        story.last_update_at,
        story.title_ru ?? null,
        story.summary_ru ?? null,
        story.summary_version ?? 0,
        story.category ?? 'other',
        story.risk_level ?? 'low',
        story.state ?? 'published',
        story.hashtags ?? null,
      ),
    );

    // Upsert each item + story_items join
    for (const item of story.items ?? []) {
      stmts.push(
        env.DB.prepare(`
          INSERT OR IGNORE INTO items (
            item_id, source_id, source_url, normalized_url, item_key,
            title_he, published_at, date_confidence, ingested_at, status
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        `).bind(
          item.item_id,
          item.source_id,
          item.source_url,
          item.normalized_url,
          item.item_key,
          item.title_he,
          item.published_at ?? null,
          item.date_confidence ?? 'low',
          item.ingested_at,
        ),
      );

      stmts.push(
        env.DB.prepare(`
          INSERT OR IGNORE INTO story_items (story_id, item_id, added_at, rank)
          VALUES (?, ?, ?, 0)
        `).bind(story.story_id, item.item_id, item.ingested_at),
      );
    }

    // Upsert publication row — mark as published on the web
    stmts.push(
      env.DB.prepare(`
        INSERT INTO publications (story_id, web_status, web_published_at)
        VALUES (?, 'published', ?)
        ON CONFLICT(story_id) DO UPDATE SET
          web_status       = 'published',
          web_published_at = COALESCE(publications.web_published_at, excluded.web_published_at)
      `).bind(story.story_id, story.last_update_at),
    );

    await env.DB.batch(stmts);
    synced++;
  }

  return jsonResp({ ok: true, synced });
}
