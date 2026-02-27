import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { fetchRss } from '../src/ingest/rss';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_XML = readFileSync(
  join(__dirname, 'fixtures', 'ynet_main.xml'),
  'utf-8',
);

function mockFetch(xml: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(xml),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// fetchRss — happy path
// ---------------------------------------------------------------------------
describe('fetchRss — happy path', () => {
  it('returns two entries from the ynet fixture', async () => {
    mockFetch(FIXTURE_XML);
    const entries = await fetchRss('https://example.com/rss', 10);
    expect(entries).toHaveLength(2);
  });

  it('strips UTM params from item 1 normalizedUrl', async () => {
    mockFetch(FIXTURE_XML);
    const [first] = await fetchRss('https://example.com/rss', 10);
    expect(first?.normalizedUrl).not.toContain('utm_source');
    expect(first?.normalizedUrl).not.toContain('utm_medium');
    // non-tracking param is preserved
    expect(first?.normalizedUrl).toContain('keep=yes');
  });

  it('item 1 has high dateConfidence and ISO publishedAt', async () => {
    mockFetch(FIXTURE_XML);
    const [first] = await fetchRss('https://example.com/rss', 10);
    expect(first?.dateConfidence).toBe('high');
    expect(first?.publishedAt).not.toBeNull();
    // Must be parseable ISO-8601
    expect(() => new Date(first!.publishedAt!)).not.toThrow();
    expect(isNaN(new Date(first!.publishedAt!).getTime())).toBe(false);
  });

  it('item 2 has low dateConfidence and null publishedAt', async () => {
    mockFetch(FIXTURE_XML);
    const entries = await fetchRss('https://example.com/rss', 10);
    const second = entries[1];
    expect(second?.dateConfidence).toBe('low');
    expect(second?.publishedAt).toBeNull();
  });

  it('strips HTML tags from description (snippet)', async () => {
    mockFetch(FIXTURE_XML);
    const [first] = await fetchRss('https://example.com/rss', 10);
    expect(first?.snippetHe).not.toContain('<b>');
    expect(first?.snippetHe).not.toContain('</b>');
    expect(first?.snippetHe).toContain('ראשון');
  });

  it('itemKey is a 64-char hex string (sha256)', async () => {
    mockFetch(FIXTURE_XML);
    const [first] = await fetchRss('https://example.com/rss', 10);
    expect(first?.itemKey).toMatch(/^[0-9a-f]{64}$/);
  });

  it('respects maxItems limit', async () => {
    mockFetch(FIXTURE_XML);
    const entries = await fetchRss('https://example.com/rss', 1);
    expect(entries).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// fetchRss — error handling
// ---------------------------------------------------------------------------
describe('fetchRss — error handling', () => {
  it('throws on non-ok HTTP response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );
    await expect(fetchRss('https://example.com/rss', 10)).rejects.toThrow(
      'HTTP 503',
    );
  });

  it('throws when validateUrlForFetch rejects a private IP', async () => {
    await expect(fetchRss('http://127.0.0.1/rss', 10)).rejects.toThrow(
      'Disallowed private IP',
    );
  });
});
