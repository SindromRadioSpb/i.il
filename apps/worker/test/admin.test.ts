import { describe, expect, it } from 'vitest';
import { route } from '../src/router';
import type { Env } from '../src/index';

// ---------------------------------------------------------------------------
// DB stub helpers
// ---------------------------------------------------------------------------

function makeDb(runs: object[] = [], errors: object[] = []): D1Database {
  const stmt = {
    bind: () => stmt,
    first: <T>() => Promise.resolve(null as T | null),
    all: <T>(query?: string) => {
      // Very simple routing: if the SQL contains 'error_events' return errors, else runs
      void query;
      return Promise.resolve({ results: [] as T[], success: true, meta: {} });
    },
    run: () => Promise.resolve({ success: true, meta: { changes: 0 } }),
  };
  return { prepare: () => stmt } as unknown as D1Database;
}

const EMPTY_DB = makeDb();

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    DB: EMPTY_DB,
    CRON_ENABLED: 'false',
    FB_POSTING_ENABLED: 'false',
    ADMIN_ENABLED: 'false',
    CRON_INTERVAL_MIN: '10',
    MAX_NEW_ITEMS_PER_RUN: '25',
    SUMMARY_TARGET_MIN: '400',
    SUMMARY_TARGET_MAX: '700',
    ...overrides,
  } as Env;
}

const ctx = {} as ExecutionContext;

function get(path: string, env: Env) {
  return route(new Request(`http://local${path}`, { method: 'GET' }), env, ctx);
}

// ---------------------------------------------------------------------------
// Admin gate
// ---------------------------------------------------------------------------

describe('Admin gate', () => {
  it('GET /api/v1/admin/runs returns 403 when ADMIN_ENABLED is not "true"', async () => {
    const res = await get('/api/v1/admin/runs', makeEnv({ ADMIN_ENABLED: 'false' }));
    expect(res.status).toBe(403);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('forbidden');
  });

  it('GET /api/v1/admin/errors returns 403 when ADMIN_ENABLED is not "true"', async () => {
    const res = await get('/api/v1/admin/errors?run_id=x', makeEnv({ ADMIN_ENABLED: 'false' }));
    expect(res.status).toBe(403);
  });
});

// ---------------------------------------------------------------------------
// GET /api/v1/admin/runs
// ---------------------------------------------------------------------------

describe('GET /api/v1/admin/runs', () => {
  it('returns 200 with runs array when admin is enabled', async () => {
    const res = await get('/api/v1/admin/runs', makeEnv({ ADMIN_ENABLED: 'true', DB: EMPTY_DB }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; data: { runs: unknown[] } };
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.data.runs)).toBe(true);
  });

  it('returns data from DB when runs exist', async () => {
    const runRow = {
      run_id: 'run-1',
      started_at: '2026-02-28T05:00:00Z',
      finished_at: '2026-02-28T05:00:10Z',
      status: 'success',
      sources_ok: 8,
      sources_failed: 0,
      items_found: 40,
      items_new: 5,
      stories_new: 2,
      stories_updated: 3,
      published_web: 2,
      published_fb: 2,
      errors_total: 0,
      duration_ms: 10000,
    };
    const stmt = {
      bind: function() { return this; },
      first: <T>() => Promise.resolve(runRow as unknown as T),
      all: <T>() => Promise.resolve({ results: [runRow] as unknown as T[], success: true, meta: {} }),
      run: () => Promise.resolve({ success: true, meta: { changes: 0 } }),
    };
    const db = { prepare: () => stmt } as unknown as D1Database;

    const res = await get('/api/v1/admin/runs', makeEnv({ ADMIN_ENABLED: 'true', DB: db }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; data: { runs: typeof runRow[] } };
    expect(body.data.runs).toHaveLength(1);
    expect(body.data.runs[0]!.run_id).toBe('run-1');
    expect(body.data.runs[0]!.status).toBe('success');
  });
});

// ---------------------------------------------------------------------------
// GET /api/v1/admin/errors
// ---------------------------------------------------------------------------

describe('GET /api/v1/admin/errors', () => {
  it('returns 400 when run_id is missing', async () => {
    const res = await get('/api/v1/admin/errors', makeEnv({ ADMIN_ENABLED: 'true' }));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { ok: boolean; error: { code: string } };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe('invalid_request');
  });

  it('returns 200 with errors array for a valid run_id', async () => {
    const res = await get('/api/v1/admin/errors?run_id=run-abc', makeEnv({ ADMIN_ENABLED: 'true', DB: EMPTY_DB }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; data: { errors: unknown[] } };
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.data.errors)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// GET /api/v1/health — top_failing_sources field
// ---------------------------------------------------------------------------

describe('GET /api/v1/health — enriched response', () => {
  it('includes top_failing_sources array in response', async () => {
    const res = await get('/api/v1/health', makeEnv({ ADMIN_ENABLED: 'true', DB: EMPTY_DB }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; top_failing_sources: unknown };
    expect(body.ok).toBe(true);
    expect(Array.isArray(body.top_failing_sources)).toBe(true);
  });
});
