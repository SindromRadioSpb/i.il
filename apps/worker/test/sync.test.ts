/**
 * test/sync.test.ts — POST /api/v1/sync/stories tests.
 *
 * Uses a stateful DB mock that records batch() calls so we can verify
 * the correct number of D1 batches were executed.
 */

import { describe, expect, it } from 'vitest';
import { route } from '../src/router';

// ─────────────────────────────────────────────────────────────────────────────
// DB mock that supports batch() and records calls
// ─────────────────────────────────────────────────────────────────────────────

function makeSyncDb(): { db: D1Database; batchCalls: D1PreparedStatement[][] } {
  const batchCalls: D1PreparedStatement[][] = [];
  const stmt = {
    bind: (..._args: unknown[]) => stmt,
    first: <T>() => Promise.resolve(null as T | null),
    all: <T>() => Promise.resolve({ results: [] as T[], success: true, meta: {} }),
    run: () => Promise.resolve({ success: true, meta: { changes: 0 } }),
  } as unknown as D1PreparedStatement;

  const db = {
    prepare: (_sql: string) => stmt,
    batch: (stmts: D1PreparedStatement[]) => {
      batchCalls.push(stmts);
      return Promise.resolve([]);
    },
  } as unknown as D1Database;

  return { db, batchCalls };
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

const BASE_ENV = {
  CRON_ENABLED: 'false',
  FB_POSTING_ENABLED: 'false',
  ADMIN_ENABLED: 'false',
  CRON_INTERVAL_MIN: '10',
  MAX_NEW_ITEMS_PER_RUN: '25',
  SUMMARY_TARGET_MIN: '400',
  SUMMARY_TARGET_MAX: '700',
} as const;

const ctx = {} as Parameters<typeof route>[2];

// Token used in success/validation tests — must match CF_SYNC_TOKEN in ENV below
const TEST_TOKEN = 'test-token';

function makeRequest(body: unknown, token = TEST_TOKEN): Request {
  return new Request('http://local/api/v1/sync/stories', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

const SAMPLE_STORY = {
  story_id: 'abc123',
  start_at: '2026-02-28T10:00:00.000Z',
  last_update_at: '2026-02-28T11:00:00.000Z',
  title_ru: 'Test story',
  summary_ru: 'Test summary',
  category: 'other',
  risk_level: 'low',
  state: 'published',
  summary_version: 1,
  hashtags: null,
  items: [],
};

// ─────────────────────────────────────────────────────────────────────────────
// Auth tests
// ─────────────────────────────────────────────────────────────────────────────

describe('POST /api/v1/sync/stories — auth', () => {
  it('returns 403 when CF_SYNC_TOKEN is not configured', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db };
    const req = makeRequest({ stories: [] });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(403);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('sync_disabled');
  });

  it('returns 401 when Authorization header is missing', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: 'secret' };
    const req = new Request('http://local/api/v1/sync/stories', { method: 'POST' });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(401);
  });

  it('returns 401 when token is wrong', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: 'correct-token' };
    const req = makeRequest({ stories: [] }, 'wrong-token');
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(401);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('unauthorized');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Validation tests
// ─────────────────────────────────────────────────────────────────────────────

describe('POST /api/v1/sync/stories — validation', () => {
  it('returns 400 on invalid JSON', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const req = new Request('http://local/api/v1/sync/stories', {
      method: 'POST',
      headers: { authorization: `Bearer ${TEST_TOKEN}`, 'content-type': 'application/json' },
      body: 'not valid json !!!',
    });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(400);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.error.code).toBe('invalid_json');
  });

  it('returns 400 when stories field is missing', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const req = makeRequest({ not_stories: [] });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(400);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.error.code).toBe('invalid_request');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Success tests
// ─────────────────────────────────────────────────────────────────────────────

describe('POST /api/v1/sync/stories — success', () => {
  it('returns 200 with synced=0 for empty stories array', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const req = makeRequest({ stories: [] });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; synced: number };
    expect(body.ok).toBe(true);
    expect(body.synced).toBe(0);
  });

  it('returns synced count equal to number of stories', async () => {
    const { db } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const req = makeRequest({
      stories: [SAMPLE_STORY, { ...SAMPLE_STORY, story_id: 'xyz789' }],
    });
    const res = await route(req, env as Parameters<typeof route>[1], ctx);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; synced: number };
    expect(body.ok).toBe(true);
    expect(body.synced).toBe(2);
  });

  it('calls DB batch once per story', async () => {
    const { db, batchCalls } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const req = makeRequest({
      stories: [SAMPLE_STORY, { ...SAMPLE_STORY, story_id: 'xyz789' }],
    });
    await route(req, env as Parameters<typeof route>[1], ctx);
    expect(batchCalls).toHaveLength(2);
  });

  it('includes item statements in batch when story has items', async () => {
    const { db, batchCalls } = makeSyncDb();
    const env = { ...BASE_ENV, DB: db, CF_SYNC_TOKEN: TEST_TOKEN };
    const storyWithItems = {
      ...SAMPLE_STORY,
      items: [
        {
          item_id: 'item1',
          source_id: 'ynet',
          source_url: 'https://ynet.co.il/1',
          normalized_url: 'https://ynet.co.il/1',
          item_key: 'key1',
          title_he: 'כותרת',
          published_at: '2026-02-28T10:00:00.000Z',
          date_confidence: 'high',
          ingested_at: '2026-02-28T10:00:00.000Z',
        },
      ],
    };
    const req = makeRequest({ stories: [storyWithItems] });
    await route(req, env as Parameters<typeof route>[1], ctx);
    // 1 batch per story; batch should contain story stmt + 2 per item (item + story_item) + 1 publication
    expect(batchCalls).toHaveLength(1);
    expect(batchCalls[0]!.length).toBeGreaterThan(2); // story + items + publication
  });
});
