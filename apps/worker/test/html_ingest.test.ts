import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { fetchHtmlNews } from '../src/ingest/html';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PAGE_HTML = readFileSync(join(__dirname, 'fixtures', 'ynet_news_page.html'), 'utf-8');
const ARTICLE_A = readFileSync(join(__dirname, 'fixtures', 'ynet_article_aa11bb22.html'), 'utf-8');
const ARTICLE_B = readFileSync(join(__dirname, 'fixtures', 'ynet_article_cc33dd44.html'), 'utf-8');

function mockFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | Request) => {
      const url = String(input);

      if (url === 'https://www.ynet.co.il/news') {
        return { ok: true, status: 200, text: async (): Promise<string> => PAGE_HTML };
      }
      if (url === 'https://www.ynet.co.il/news/article/aa11bb22') {
        return { ok: true, status: 200, text: async (): Promise<string> => ARTICLE_A };
      }
      if (url === 'https://www.ynet.co.il/news/article/cc33dd44') {
        return { ok: true, status: 200, text: async (): Promise<string> => ARTICLE_B };
      }

      return {
        ok: false,
        status: 404,
        headers: { get: () => null },
        text: async (): Promise<string> => '',
      };
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchHtmlNews', () => {
  it('extracts ynet news article links and parses entries', async () => {
    mockFetch();
    const entries = await fetchHtmlNews('https://www.ynet.co.il/news', 10);
    expect(entries).toHaveLength(2);
    expect(entries[0]?.sourceUrl).toBe('https://www.ynet.co.il/news/article/aa11bb22');
    expect(entries[1]?.sourceUrl).toBe('https://www.ynet.co.il/news/article/cc33dd44');
  });

  it('sets high dateConfidence when published_time exists', async () => {
    mockFetch();
    const entries = await fetchHtmlNews('https://www.ynet.co.il/news', 10);
    expect(entries[0]?.dateConfidence).toBe('high');
    expect(entries[0]?.publishedAt).not.toBeNull();
  });

  it('sets low dateConfidence when published_time is missing', async () => {
    mockFetch();
    const entries = await fetchHtmlNews('https://www.ynet.co.il/news', 10);
    expect(entries[1]?.dateConfidence).toBe('low');
    expect(entries[1]?.publishedAt).toBeNull();
  });

  it('deduplicates repeated links', async () => {
    mockFetch();
    const entries = await fetchHtmlNews('https://www.ynet.co.il/news', 10);
    const urls = entries.map(e => e.normalizedUrl);
    expect(new Set(urls).size).toBe(urls.length);
  });

  it('respects maxItems', async () => {
    mockFetch();
    const entries = await fetchHtmlNews('https://www.ynet.co.il/news', 1);
    expect(entries).toHaveLength(1);
  });

  it('rejects private host URL', async () => {
    await expect(fetchHtmlNews('http://127.0.0.1/news', 10)).rejects.toThrow(
      'Disallowed private IP',
    );
  });
});
