import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { postToFacebook, runFbCrosspost } from '../src/fb/post';
import type { Env } from '../src/index';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    DB: {} as unknown as Env['DB'],
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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// postToFacebook
// ---------------------------------------------------------------------------

describe('postToFacebook', () => {
  it('sends correct POST request and returns post ID', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: '12345_67890' }),
      }),
    );

    const postId = await postToFacebook('PAGE_ID', 'TOKEN', 'Hello', 'https://example.com');

    expect(postId).toBe('12345_67890');
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/PAGE_ID/feed');
    expect(url).toContain('graph.facebook.com');
    const body = JSON.parse(init.body as string) as Record<string, string>;
    expect(body.message).toBe('Hello');
    expect(body.link).toBe('https://example.com');
    expect(body.access_token).toBe('TOKEN');
  });

  it('throws on non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: { code: 100, message: 'bad param' } }),
      }),
    );

    await expect(postToFacebook('P', 'T', 'msg', 'link')).rejects.toThrow('Facebook API 400');
  });

  it('throws on response missing id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({}),
      }),
    );

    await expect(postToFacebook('P', 'T', 'msg', 'link')).rejects.toThrow('missing post id');
  });
});

// ---------------------------------------------------------------------------
// runFbCrosspost — guard conditions
// ---------------------------------------------------------------------------

describe('runFbCrosspost — guards', () => {
  it('returns zeros when FB_POSTING_ENABLED is not "true"', async () => {
    const env = makeEnv({ FB_POSTING_ENABLED: 'false' });
    const result = await runFbCrosspost(env, 'run-1');
    expect(result).toEqual({ posted: 0, failed: 0 });
  });

  it('returns zeros when FB_PAGE_ACCESS_TOKEN is missing', async () => {
    const env = makeEnv({ FB_POSTING_ENABLED: 'true', FB_PAGE_ID: 'PAGE_ID' });
    const result = await runFbCrosspost(env, 'run-2');
    expect(result).toEqual({ posted: 0, failed: 0 });
  });

  it('returns zeros when FB_PAGE_ID is missing', async () => {
    const env = makeEnv({ FB_POSTING_ENABLED: 'true', FB_PAGE_ACCESS_TOKEN: 'TOKEN' });
    const result = await runFbCrosspost(env, 'run-3');
    expect(result).toEqual({ posted: 0, failed: 0 });
  });
});

// ---------------------------------------------------------------------------
// runFbCrosspost — happy path
// ---------------------------------------------------------------------------

describe('runFbCrosspost — posting', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: 'post-abc' }),
      }),
    );
  });

  it('posts stories and returns correct counters', async () => {
    const dbStub = {
      prepare: vi.fn().mockReturnValue({
        bind: vi.fn().mockReturnValue({
          all: vi.fn().mockResolvedValue({
            results: [
              {
                story_id: 'story-1',
                title_ru: 'Заголовок 1',
                summary_ru: 'Строка 1\nСтрока 2\nСтрока 3',
              },
            ],
          }),
          run: vi.fn().mockResolvedValue({}),
        }),
      }),
    };

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    const result = await runFbCrosspost(env, 'run-ok');
    expect(result.posted).toBe(1);
    expect(result.failed).toBe(0);
  });

  it('message includes title and first 2 lines of summary and link', async () => {
    const dbStub = {
      prepare: vi.fn().mockReturnValue({
        bind: vi.fn().mockReturnValue({
          all: vi.fn().mockResolvedValue({
            results: [
              {
                story_id: 'story-2',
                title_ru: 'Мой Заголовок',
                summary_ru: 'Первая строка\nВторая строка\nТретья строка',
              },
            ],
          }),
          run: vi.fn().mockResolvedValue({}),
        }),
      }),
    };

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    await runFbCrosspost(env, 'run-msg');

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string) as Record<string, string>;
    expect(body.message).toContain('📌 Мой Заголовок');
    expect(body.message).toContain('Первая строка');
    expect(body.message).toContain('Вторая строка');
    expect(body.message).not.toContain('Третья строка');
    expect(body.message).toContain('/story/story-2');
    expect(body.link).toBe('https://news.example.com/story/story-2');
  });
});

// ---------------------------------------------------------------------------
// runFbCrosspost — error handling
// ---------------------------------------------------------------------------

describe('runFbCrosspost — error handling', () => {
  it('marks story as auth_error on FB code 190 and stops further posts', async () => {
    const runCalls: string[] = [];
    const dbStub = {
      prepare: vi.fn().mockReturnValue({
        bind: vi.fn().mockReturnValue({
          all: vi.fn().mockResolvedValue({
            results: [
              { story_id: 's1', title_ru: 'T1', summary_ru: 'Body' },
              { story_id: 's2', title_ru: 'T2', summary_ru: 'Body' },
            ],
          }),
          run: vi.fn().mockImplementation(() => {
            runCalls.push('run');
            return Promise.resolve({});
          }),
        }),
      }),
    };

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: { code: 190, message: 'invalid token' } }),
      }),
    );

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'BAD_TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
    });

    const result = await runFbCrosspost(env, 'run-auth-err');
    // First story fails with auth_error; second is skipped (loop break)
    expect(result.failed).toBe(1);
    expect(result.posted).toBe(0);
    // Only one FB API call (second story skipped)
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it('marks story as rate_limited on FB code 4', async () => {
    const dbStub = {
      prepare: vi.fn().mockReturnValue({
        bind: vi.fn().mockReturnValue({
          all: vi.fn().mockResolvedValue({
            results: [{ story_id: 's1', title_ru: 'T1', summary_ru: 'Body' }],
          }),
          run: vi.fn().mockResolvedValue({}),
        }),
      }),
    };

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({ error: { code: 4, message: 'rate limit' } }),
      }),
    );

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
    });

    const result = await runFbCrosspost(env, 'run-rate');
    expect(result.failed).toBe(1);
    expect(result.posted).toBe(0);
  });
});
