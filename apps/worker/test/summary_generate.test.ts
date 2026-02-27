import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { callClaude } from '../src/summary/generate';

const VALID_RESPONSE_TEXT = [
  'Заголовок: В Тель-Авиве произошло землетрясение',
  'Что произошло: Землетрясение магнитудой 4.5 произошло ранним утром.',
  'Почему важно: Это первое ощутимое землетрясение за десятилетие.',
  'Что дальше: Сейсмологи продолжают мониторинг.',
  'Источники: Ynet',
].join('\n');

function makeOkFetch(text: string) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ content: [{ type: 'text', text }] }),
    text: async () => '',
  });
}

function makeErrorFetch(status: number, body = 'error') {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    text: async () => body,
    json: async () => ({}),
  });
}

const TEST_ITEMS = [
  { titleHe: 'רעידת אדמה בתל אביב', sourceId: 'ynet_main', publishedAt: null },
];

beforeEach(() => {
  vi.stubGlobal('fetch', makeOkFetch(VALID_RESPONSE_TEXT));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
describe('callClaude — success', () => {
  it('returns the text content from the response', async () => {
    const result = await callClaude('key-123', 'claude-haiku-4-5-20251001', TEST_ITEMS, 'low');
    expect(result).toBe(VALID_RESPONSE_TEXT);
  });

  it('calls the correct Anthropic endpoint', async () => {
    await callClaude('key-123', 'claude-haiku-4-5-20251001', TEST_ITEMS, 'low');
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, unknown];
    expect(url).toBe('https://api.anthropic.com/v1/messages');
  });

  it('includes x-api-key and anthropic-version headers', async () => {
    await callClaude('my-secret-key', 'claude-haiku-4-5-20251001', TEST_ITEMS, 'low');
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit & { headers: Record<string, string> },
    ];
    expect(init.headers['x-api-key']).toBe('my-secret-key');
    expect(init.headers['anthropic-version']).toBeDefined();
  });

  it('passes the model parameter in the request body', async () => {
    const model = 'claude-haiku-4-5-20251001';
    await callClaude('key', model, TEST_ITEMS, 'low');
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit & { body: string },
    ];
    const body = JSON.parse(init.body);
    expect(body.model).toBe(model);
  });

  it('mentions high-risk requirement in system prompt for risk_level=high', async () => {
    await callClaude('key', 'model', TEST_ITEMS, 'high');
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit & { body: string },
    ];
    const body = JSON.parse(init.body);
    expect(body.system).toContain('по данным источников');
  });
});

// ---------------------------------------------------------------------------
describe('callClaude — error handling', () => {
  it('throws on non-2xx HTTP response', async () => {
    vi.stubGlobal('fetch', makeErrorFetch(429, 'rate limited'));
    await expect(
      callClaude('key', 'model', TEST_ITEMS, 'low'),
    ).rejects.toThrow('Claude API 429');
  });

  it('throws when response has no text content block', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: 'tool_use', id: 'x' }] }),
      text: async () => '',
    }));
    await expect(
      callClaude('key', 'model', TEST_ITEMS, 'low'),
    ).rejects.toThrow('no text content');
  });
});
