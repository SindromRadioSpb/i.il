import { describe, expect, it } from 'vitest';
import { route } from '../src/router';

// ---------------------------------------------------------------------------
// Minimal D1 mock (same pattern as api_feed.test.ts)
// ---------------------------------------------------------------------------
function makeDb(...calls: unknown[]): D1Database {
  let i = 0;
  const stmt = {
    bind: () => stmt,
    first: <T>() => Promise.resolve((calls[i++] ?? null) as T | null),
    all: <T>() => {
      const r = calls[i++];
      const results = Array.isArray(r) ? r : r != null ? [r] : [];
      return Promise.resolve({ results: results as T[], success: true, meta: {} });
    },
    run: () => Promise.resolve({ success: true, meta: { changes: 1 } }),
  };
  return { prepare: () => stmt } as unknown as D1Database;
}

const BASE_ENV = {
  CRON_ENABLED: 'false',
  FB_POSTING_ENABLED: 'false',
  ADMIN_ENABLED: 'false',
  CRON_INTERVAL_MIN: '10',
  MAX_NEW_ITEMS_PER_RUN: '25',
  SUMMARY_TARGET_MIN: '400',
  SUMMARY_TARGET_MAX: '700',
} as const;

const ctx = {} as ExecutionContext;

function get(path: string, db: D1Database) {
  return route(new Request(`http://local${path}`, { method: 'GET' }), { ...BASE_ENV, DB: db }, ctx);
}

// ---------------------------------------------------------------------------
// Story not found
// ---------------------------------------------------------------------------
describe('GET /api/v1/story/:id — not found', () => {
  it('returns 404 when story does not exist', async () => {
    const db = makeDb(null); // .first() returns null
    const res = await get('/api/v1/story/no-such-story', db);
    expect(res.status).toBe(404);
    const body = await res.json() as { ok: boolean; error: { code: string; details: { story_id: string } } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('not_found');
    expect(body.error.details.story_id).toBe('no-such-story');
  });
});

// ---------------------------------------------------------------------------
// Story found
// ---------------------------------------------------------------------------
describe('GET /api/v1/story/:id — found', () => {
  const storyRow = {
    story_id: 'story-abc',
    start_at: '2026-02-27T09:00:00.000Z',
    last_update_at: '2026-02-27T11:00:00.000Z',
    title_ru: 'Тестовая история',
    summary_ru: 'Подробное описание событий.',
    category: 'security',
    risk_level: 'medium',
    state: 'draft',
  };

  const timelineRows = [
    {
      item_id: 'item-1',
      source_id: 'ynet_main',
      title_he: 'כותרת ראשונה',
      url: 'https://www.ynet.co.il/news/article/1',
      published_at: '2026-02-27T09:00:00.000Z',
      updated_at: null,
    },
    {
      item_id: 'item-2',
      source_id: 'mako_news',
      title_he: 'כותרת שנייה',
      url: 'https://rcs.mako.co.il/article/2',
      published_at: '2026-02-27T10:00:00.000Z',
      updated_at: null,
    },
  ];

  it('returns 200 with story data', async () => {
    const db = makeDb(storyRow, timelineRows);
    const res = await get('/api/v1/story/story-abc', db);
    expect(res.status).toBe(200);
    const body = await res.json() as { ok: boolean; data: { story: Record<string, unknown> } };
    expect(body.ok).toBe(true);
    const s = body.data.story;
    expect(s['story_id']).toBe('story-abc');
    expect(s['title_ru']).toBe('Тестовая история');
    expect(s['canonical_url']).toBe('/story/story-abc');
    expect(s['category']).toBe('security');
    expect(s['risk_level']).toBe('medium');
  });

  it('returns timeline items', async () => {
    const db = makeDb(storyRow, timelineRows);
    const res = await get('/api/v1/story/story-abc', db);
    const body = await res.json() as { data: { story: { timeline: unknown[] } } };
    expect(body.data.story.timeline).toHaveLength(2);
  });

  it('returns deduplicated sources from registry', async () => {
    const db = makeDb(storyRow, timelineRows);
    const res = await get('/api/v1/story/story-abc', db);
    const body = await res.json() as {
      data: { story: { sources: { source_id: string; name: string; url: string }[] } };
    };
    const sources = body.data.story.sources;
    expect(sources.length).toBe(2); // ynet_main + mako_news
    expect(sources.every(s => typeof s.name === 'string')).toBe(true);
    expect(sources.every(s => typeof s.url === 'string')).toBe(true);
  });

  it('returns empty sources for unknown source_id', async () => {
    const rowsWithUnknownSource = [
      { ...timelineRows[0]!, source_id: 'unknown_source_xyz' },
    ];
    const db = makeDb(storyRow, rowsWithUnknownSource);
    const res = await get('/api/v1/story/story-abc', db);
    const body = await res.json() as { data: { story: { sources: unknown[] } } };
    expect(body.data.story.sources).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 500 guard — DB throws unexpectedly
// ---------------------------------------------------------------------------
describe('GET /api/v1/story/:id — DB error', () => {
  it('returns 500 when DB throws', async () => {
    const badDb = {
      prepare: () => { throw new Error('DB unavailable'); },
    } as unknown as D1Database;
    const res = await get('/api/v1/story/any', badDb);
    expect(res.status).toBe(500);
    const body = await res.json() as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('internal_error');
  });
});
