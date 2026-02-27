import { describe, expect, it } from 'vitest';
import { route } from '../src/router';

// Stateless D1 mock: always returns null for .first() and [] for .all().
// Sufficient for health/feed/story tests that expect empty/not-found state.
const EMPTY_DB: D1Database = (() => {
  const stmt = {
    bind: () => stmt,
    first: <T>() => Promise.resolve(null as T | null),
    all: <T>() => Promise.resolve({ results: [] as T[], success: true, meta: {} }),
    run: () => Promise.resolve({ success: true, meta: { changes: 0 } }),
  };
  return { prepare: () => stmt } as unknown as D1Database;
})();

const ENV = {
  DB: EMPTY_DB,
  CRON_ENABLED: 'false',
  FB_POSTING_ENABLED: 'false',
  ADMIN_ENABLED: 'true',
  CRON_INTERVAL_MIN: '10',
  MAX_NEW_ITEMS_PER_RUN: '25',
  SUMMARY_TARGET_MIN: '400',
  SUMMARY_TARGET_MAX: '700',
} as const;

const ctx = {} as any;

function get(path: string) {
  return route(new Request(`http://local${path}`, { method: 'GET' }), ENV, ctx);
}

// ---------------------------------------------------------------------------
// GET /api/v1/health
// ---------------------------------------------------------------------------
describe('GET /api/v1/health', () => {
  it('returns 200 with correct contract shape', async () => {
    const res = await get('/api/v1/health');
    expect(res.status).toBe(200);

    const body = (await res.json()) as Record<string, unknown>;
    expect(body.ok).toBe(true);

    // service block
    const service = body.service as Record<string, unknown>;
    expect(typeof service.name).toBe('string');
    expect(typeof service.version).toBe('string');
    expect(['dev', 'staging', 'prod']).toContain(service.env);
    expect(typeof service.now_utc).toBe('string');
    // must be valid ISO-8601
    expect(() => new Date(service.now_utc as string)).not.toThrow();

    // last_run: null or object — currently null (no DB yet)
    expect(body.last_run === null || typeof body.last_run === 'object').toBe(true);
  });

  it('env=dev when ADMIN_ENABLED=true', async () => {
    const res = await get('/api/v1/health');
    const body = (await res.json()) as { service: { env: string } };
    expect(body.service.env).toBe('dev');
  });
});

// ---------------------------------------------------------------------------
// GET /api/v1/feed
// ---------------------------------------------------------------------------
describe('GET /api/v1/feed', () => {
  it('returns 200 with empty stories list', async () => {
    const res = await get('/api/v1/feed');
    expect(res.status).toBe(200);

    const body = (await res.json()) as {
      ok: boolean;
      data: { stories: unknown[]; next_cursor: unknown };
    };
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.data.stories)).toBe(true);
    expect(body.data.stories).toHaveLength(0);
    expect(body.data.next_cursor).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// GET /api/v1/story/:id
// ---------------------------------------------------------------------------
describe('GET /api/v1/story/:id', () => {
  it('returns 404 not_found with story_id in details', async () => {
    const res = await get('/api/v1/story/abc-123');
    expect(res.status).toBe(404);

    const body = (await res.json()) as {
      ok: boolean;
      error: { code: string; details: { story_id: string } };
    };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('not_found');
    expect(body.error.details.story_id).toBe('abc-123');
  });

  it('story_id is passed through correctly', async () => {
    const res = await get('/api/v1/story/xyz-456');
    const body = (await res.json()) as { error: { details: { story_id: string } } };
    expect(body.error.details.story_id).toBe('xyz-456');
  });
});

// ---------------------------------------------------------------------------
// Unknown routes → 404 fallback
// ---------------------------------------------------------------------------
describe('404 fallback', () => {
  it('unknown path returns 404 not_found', async () => {
    const res = await get('/api/v1/unknown');
    expect(res.status).toBe(404);

    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('not_found');
  });
});
