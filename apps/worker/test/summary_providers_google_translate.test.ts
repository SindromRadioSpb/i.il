import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { GoogleTranslateProvider } from '../src/summary/providers/google_translate';
import type { Env } from '../src/index';

const ITEMS = [
  { itemId: 'i1', titleHe: 'כותרת ראשית', sourceId: 'ynet_main', publishedAt: null },
];

// Google Translate unofficial API response format:
// [[[segment_translated, segment_source, null, null, N], ...], null, "iw"]
function makeGtResponse(translated: string) {
  return [[[translated, 'כותרת ראשית', null, null, 10]], null, 'iw'];
}

const FAKE_ENV = {} as Env;

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => makeGtResponse('Главный заголовок'),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GoogleTranslateProvider', () => {
  it('returns all 5 required sections', async () => {
    const provider = new GoogleTranslateProvider();
    const result = await provider.generate(ITEMS, 'low', FAKE_ENV);
    expect(result).toContain('Заголовок:');
    expect(result).toContain('Что произошло:');
    expect(result).toContain('Почему важно:');
    expect(result).toContain('Что дальше:');
    expect(result).toContain('Источники:');
  });

  it('uses translated Russian text in headline, not Hebrew', async () => {
    const provider = new GoogleTranslateProvider();
    const result = await provider.generate(ITEMS, 'low', FAKE_ENV);
    expect(result).toContain('Главный заголовок');
    expect(result).not.toContain('כותרת ראשית');
  });

  it('calls Google Translate API with correct parameters', async () => {
    const provider = new GoogleTranslateProvider();
    await provider.generate(ITEMS, 'low', FAKE_ENV);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain('translate.googleapis.com');
    expect(url).toContain('client=gtx');
    expect(url).toContain('sl=he');
    expect(url).toContain('tl=ru');
  });

  it('throws on non-2xx HTTP response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 429 }),
    );
    const provider = new GoogleTranslateProvider();
    await expect(provider.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow(
      'Google Translate HTTP 429',
    );
  });

  it('throws on unexpected response shape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ error: 'bad shape' }),
      }),
    );
    const provider = new GoogleTranslateProvider();
    await expect(provider.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow(
      'unexpected response shape',
    );
  });

  it('throws when no segments returned', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [[], null, 'iw'],
      }),
    );
    const provider = new GoogleTranslateProvider();
    await expect(provider.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow(
      'no translation segments',
    );
  });

  it('uses high-risk attribution when riskLevel is high', async () => {
    const provider = new GoogleTranslateProvider();
    const result = await provider.generate(ITEMS, 'high', FAKE_ENV);
    expect(result).toContain('повышенного внимания');
  });

  it('combines multiple items into Что произошло section', async () => {
    const items = [
      { itemId: 'i1', titleHe: 'כותרת 1', sourceId: 'ynet_main', publishedAt: null },
      { itemId: 'i2', titleHe: 'כותרת 2', sourceId: 'mako_news', publishedAt: null },
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => makeGtResponse('Заголовок первый'),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => makeGtResponse('Заголовок второй'),
        }),
    );
    const provider = new GoogleTranslateProvider();
    const result = await provider.generate(items, 'low', FAKE_ENV);
    expect(result).toContain('Заголовок первый');
    expect(result).toContain('Заголовок второй');
  });
});
