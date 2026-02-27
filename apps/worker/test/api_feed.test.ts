import { describe, expect, it } from 'vitest';
import { route } from '../src/router';
import { encodeCursor } from '../src/api/cursor';

// ---------------------------------------------------------------------------
// Minimal D1 mock: each call to .first() or .all() consumes the next queued result.
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
// Feed — basic shape
// ---------------------------------------------------------------------------
describe('GET /api/v1/feed — empty', () => {
  it('returns 200 with empty stories array', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed', db);
    expect(res.status).toBe(200);
    const body = await res.json() as { ok: boolean; data: { stories: unknown[]; next_cursor: unknown } };
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.data.stories)).toBe(true);
    expect(body.data.stories).toHaveLength(0);
    expect(body.data.next_cursor).toBeNull();
  });
});

describe('GET /api/v1/feed — with stories', () => {
  const storyRow = {
    story_id: 'story-1',
    start_at: '2026-02-27T10:00:00.000Z',
    last_update_at: '2026-02-27T11:00:00.000Z',
    title_ru: 'Тест история',
    summary_ru: 'Краткое описание',
    category: 'politics',
    risk_level: 'low',
    source_count: 2,
  };

  it('returns story with correct shape', async () => {
    const db = makeDb([storyRow]);
    const res = await get('/api/v1/feed', db);
    expect(res.status).toBe(200);
    const body = await res.json() as { ok: boolean; data: { stories: Record<string, unknown>[] } };
    const s = body.data.stories[0]!;
    expect(s['story_id']).toBe('story-1');
    expect(s['canonical_url']).toBe('/story/story-1');
    expect(s['title_ru']).toBe('Тест история');
    expect(s['category']).toBe('politics');
    expect(s['source_count']).toBe(2);
  });

  it('summary_excerpt_ru is truncated to 250 chars', async () => {
    const longSummary = 'А'.repeat(400);
    const db = makeDb([{ ...storyRow, summary_ru: longSummary }]);
    const res = await get('/api/v1/feed', db);
    const body = await res.json() as { data: { stories: { summary_excerpt_ru: string }[] } };
    expect(body.data.stories[0]!.summary_excerpt_ru.length).toBeLessThanOrEqual(250);
  });

  it('produces next_cursor when rows exceed limit', async () => {
    // Return limit+1 rows to trigger next_cursor
    const rows = Array.from({ length: 21 }, (_, idx) => ({
      ...storyRow,
      story_id: `story-${idx}`,
      last_update_at: `2026-02-27T${String(11 + idx).padStart(2, '0')}:00:00.000Z`,
    }));
    const db = makeDb(rows);
    const res = await get('/api/v1/feed?limit=20', db);
    const body = await res.json() as { data: { stories: unknown[]; next_cursor: string | null } };
    expect(body.data.stories).toHaveLength(20);
    expect(body.data.next_cursor).not.toBeNull();
  });

  it('no next_cursor when rows <= limit', async () => {
    const db = makeDb([storyRow]);
    const res = await get('/api/v1/feed?limit=20', db);
    const body = await res.json() as { data: { next_cursor: null } };
    expect(body.data.next_cursor).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Feed — cursor decoding
// ---------------------------------------------------------------------------
describe('GET /api/v1/feed — cursor param', () => {
  it('accepts a valid cursor without error', async () => {
    const cursor = encodeCursor('2026-02-27T10:00:00.000Z', 'story-1');
    const db = makeDb([]);
    const res = await get(`/api/v1/feed?cursor=${cursor}`, db);
    expect(res.status).toBe(200);
  });

  it('returns 400 for malformed cursor', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed?cursor=!!!invalid!!!', db);
    expect(res.status).toBe(400);
    const body = await res.json() as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// Feed — limit validation
// ---------------------------------------------------------------------------
describe('GET /api/v1/feed — limit validation', () => {
  it('returns 400 for limit > 50', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed?limit=99', db);
    expect(res.status).toBe(400);
    const body = await res.json() as { error: { code: string } };
    expect(body.error.code).toBe('invalid_request');
  });

  it('returns 400 for limit=0', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed?limit=0', db);
    expect(res.status).toBe(400);
  });

  it('returns 400 for non-numeric limit', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed?limit=abc', db);
    expect(res.status).toBe(400);
  });

  it('returns 200 for limit=50 (max)', async () => {
    const db = makeDb([]);
    const res = await get('/api/v1/feed?limit=50', db);
    expect(res.status).toBe(200);
  });
});
