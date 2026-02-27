import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { GeminiProvider } from '../src/summary/providers/gemini';
import type { Env } from '../src/index';

const ITEMS = [
  { itemId: 'i1', titleHe: 'כותרת ראשית', sourceId: 'ynet_main', publishedAt: null },
];

const VALID_TEXT = 'Заголовок: Тест\nЧто произошло: Событие.\nПочему важно: Важно.\nЧто дальше: Ожидается обновление.\nИсточники: Ynet';

function makeEnv(overrides: Partial<Env> = {}): Env {
  return { GEMINI_API_KEY: 'test-key', ...overrides } as Env;
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      candidates: [{ content: { parts: [{ text: VALID_TEXT }] } }],
    }),
    text: async () => '',
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GeminiProvider', () => {
  it('returns generated text on success', async () => {
    const provider = new GeminiProvider();
    const result = await provider.generate(ITEMS, 'low', makeEnv());
    expect(result).toBe(VALID_TEXT);
  });

  it('throws when GEMINI_API_KEY is not set', async () => {
    const provider = new GeminiProvider();
    await expect(provider.generate(ITEMS, 'low', {} as Env)).rejects.toThrow('GEMINI_API_KEY');
  });

  it('calls the correct Gemini endpoint', async () => {
    const provider = new GeminiProvider();
    await provider.generate(ITEMS, 'low', makeEnv());
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, unknown];
    expect(url).toContain('generativelanguage.googleapis.com');
    expect(url).toContain('gemini-2.0-flash');
    expect(url).toContain('test-key');
  });

  it('uses GEMINI_MODEL env override', async () => {
    const provider = new GeminiProvider();
    await provider.generate(ITEMS, 'low', makeEnv({ GEMINI_MODEL: 'gemini-1.5-flash' }));
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, unknown];
    expect(url).toContain('gemini-1.5-flash');
  });

  it('throws on non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      text: async () => 'rate limited',
      json: async () => ({}),
    }));
    const provider = new GeminiProvider();
    await expect(provider.generate(ITEMS, 'low', makeEnv())).rejects.toThrow('Gemini API 429');
  });

  it('throws when response has no text content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ candidates: [] }),
      text: async () => '',
    }));
    const provider = new GeminiProvider();
    await expect(provider.generate(ITEMS, 'low', makeEnv())).rejects.toThrow('no text content');
  });
});
