import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { postToFacebook, runFbCrosspost } from '../src/fb/post';
import type { Env } from '../src/index';

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

function makeDbWithStories(stories: object[]) {
  return {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnValue({
        all: vi.fn().mockResolvedValue({ results: stories }),
        run: vi.fn().mockResolvedValue({}),
      }),
    }),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('postToFacebook', () => {
  it('posts to /photos and returns post id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ post_id: '123_456' }),
      }),
    );

    const postId = await postToFacebook(
      'PAGE_ID',
      'TOKEN',
      'caption text',
      'https://cdn.example.com/image.jpg',
    );

    expect(postId).toBe('123_456');
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/PAGE_ID/photos');
    const body = String(init.body ?? '');
    expect(body).toContain('url=https%3A%2F%2Fcdn.example.com%2Fimage.jpg');
    expect(body).toContain('access_token=TOKEN');
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

    await expect(
      postToFacebook('PAGE_ID', 'TOKEN', 'caption', 'https://cdn.example.com/img.jpg'),
    ).rejects.toThrow('Facebook API 400');
  });
});

describe('runFbCrosspost guards', () => {
  it('returns zeros when FB_POSTING_ENABLED is not true', async () => {
    const result = await runFbCrosspost(makeEnv({ FB_POSTING_ENABLED: 'false' }), 'run-1');
    expect(result).toEqual({ posted: 0, failed: 0 });
  });

  it('returns zeros when token or page id is missing', async () => {
    const r1 = await runFbCrosspost(makeEnv({ FB_POSTING_ENABLED: 'true', FB_PAGE_ID: 'P' }), 'run-2');
    const r2 = await runFbCrosspost(makeEnv({ FB_POSTING_ENABLED: 'true', FB_PAGE_ACCESS_TOKEN: 'T' }), 'run-3');
    expect(r1).toEqual({ posted: 0, failed: 0 });
    expect(r2).toEqual({ posted: 0, failed: 0 });
  });
});

describe('runFbCrosspost posting behavior', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | Request) => {
        const url = String(input);

        // article page fetch for image extraction
        if (url === 'https://www.ynet.co.il/news/article/abc') {
          return {
            ok: true,
            text: async () => '<meta property="og:image" content="https://cdn.ynet.co.il/a.jpg">',
          };
        }

        // facebook photo post
        if (url.includes('/PAGE_ID/photos')) {
          return {
            ok: true,
            json: async () => ({ post_id: 'post-abc' }),
          };
        }

        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );
  });

  it('posts one story when image is found', async () => {
    const dbStub = makeDbWithStories([
      {
        story_id: 'story-1',
        title_ru: 'Заголовок 1',
        summary_ru: 'Что произошло: факт.\nПочему важно: важно.\nЧто дальше: развитие.',
        source_url: 'https://www.ynet.co.il/news/article/abc',
      },
    ]);

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    const result = await runFbCrosspost(env, 'run-ok');
    expect(result).toEqual({ posted: 1, failed: 0 });
  });

  it('caption uses T-800 long-form style and includes links', async () => {
    const dbStub = makeDbWithStories([
      {
        story_id: 'story-2',
        title_ru: 'Региональная сводка',
        summary_ru: 'Что произошло: событие.\nПочему важно: риск.\nЧто дальше: наблюдение.',
        source_url: 'https://www.ynet.co.il/news/article/abc',
      },
    ]);

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    await runFbCrosspost(env, 'run-msg');

    const photoCall = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      call => String(call[0]).includes('/PAGE_ID/photos'),
    );
    expect(photoCall).toBeDefined();
    const body = String(photoCall?.[1]?.body ?? '');
    const decoded = decodeURIComponent(body.replace(/\+/g, '%20'));
    expect(decoded).toContain('T-800 //');
    expect(decoded).toContain('T-800:');
    expect(decoded).toContain('SARCASM MODULE:');
    expect(decoded).toContain('HUMOR MODULE:');
    expect(decoded).toContain('https://www.ynet.co.il/news/article/abc');
    expect(decoded).toContain('https://news.example.com/story/story-2');
  });

  it('fails post when article has no images', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | Request) => {
        const url = String(input);
        if (url === 'https://www.ynet.co.il/news/article/no-image') {
          return { ok: true, text: async () => '<html><head><title>No image</title></head></html>' };
        }
        if (url.includes('/PAGE_ID/photos')) {
          return { ok: true, json: async () => ({ post_id: 'post-xyz' }) };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    const dbStub = makeDbWithStories([
      {
        story_id: 'story-3',
        title_ru: 'Заголовок 3',
        summary_ru: 'Что произошло: факт.',
        source_url: 'https://www.ynet.co.il/news/article/no-image',
      },
    ]);

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    const result = await runFbCrosspost(env, 'run-no-image');
    expect(result).toEqual({ posted: 0, failed: 1 });
    const photoCalls = (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      call => String(call[0]).includes('/PAGE_ID/photos'),
    );
    expect(photoCalls.length).toBe(0);
  });

  it('marks auth_error and stops further posts on FB code 190', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | Request) => {
        const url = String(input);
        if (url.startsWith('https://www.ynet.co.il/news/article/')) {
          return {
            ok: true,
            text: async () => '<meta property="og:image" content="https://cdn.ynet.co.il/a.jpg">',
          };
        }
        if (url.includes('/PAGE_ID/photos')) {
          return {
            ok: false,
            status: 400,
            json: async () => ({ error: { code: 190, message: 'invalid token' } }),
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );

    const dbStub = makeDbWithStories([
      {
        story_id: 's1',
        title_ru: 'T1',
        summary_ru: 'Что произошло: x.',
        source_url: 'https://www.ynet.co.il/news/article/a1',
      },
      {
        story_id: 's2',
        title_ru: 'T2',
        summary_ru: 'Что произошло: y.',
        source_url: 'https://www.ynet.co.il/news/article/a2',
      },
    ]);

    const env = makeEnv({
      DB: dbStub as unknown as Env['DB'],
      FB_POSTING_ENABLED: 'true',
      FB_PAGE_ACCESS_TOKEN: 'BAD_TOKEN',
      FB_PAGE_ID: 'PAGE_ID',
      PUBLIC_SITE_BASE_URL: 'https://news.example.com',
    });

    const result = await runFbCrosspost(env, 'run-auth');
    expect(result).toEqual({ posted: 0, failed: 1 });

    const photoCalls = (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      call => String(call[0]).includes('/PAGE_ID/photos'),
    );
    expect(photoCalls.length).toBe(1);
  });
});
