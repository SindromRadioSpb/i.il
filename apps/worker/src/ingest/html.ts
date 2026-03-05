import { normalizeUrl, validateUrlForFetch } from '../normalize/url';
import { hashHex } from '../normalize/hash';
import { fetchWithTimeout } from '../net/fetch_with_timeout';
import type { NormalizedEntry } from './types';

const ARTICLE_HOST = 'www.ynet.co.il';
const ARTICLE_PATH_RE = /^\/news\/article\/[a-z0-9_-]+$/i;

function decodeHtml(raw: string): string {
  return raw
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/gi, "'")
    .replace(/&#x2f;/gi, '/')
    .replace(/&#(\d+);/g, (_m, n: string) => String.fromCharCode(Number(n)));
}

function stripHtml(html: string): string {
  return decodeHtml(html).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function parseDateToIso(raw: string | null): string | null {
  if (!raw) return null;
  const d = new Date(raw.trim());
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function getMetaContent(html: string, key: string): string | null {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const p1 = new RegExp(
    `<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']+)["'][^>]*>`,
    'i',
  );
  const m1 = html.match(p1);
  if (m1?.[1]) return decodeHtml(m1[1]).trim();

  const p2 = new RegExp(
    `<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${escaped}["'][^>]*>`,
    'i',
  );
  const m2 = html.match(p2);
  if (m2?.[1]) return decodeHtml(m2[1]).trim();

  return null;
}

function getTitle(html: string): string | null {
  const ogTitle = getMetaContent(html, 'og:title');
  if (ogTitle) return stripHtml(ogTitle);
  const t = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1];
  if (!t) return null;
  const cleaned = stripHtml(t);
  return cleaned || null;
}

function extractArticleUrls(pageUrl: string, html: string, maxItems: number): string[] {
  const hrefRe = /href\s*=\s*["']([^"']+)["']/gi;
  const seen = new Set<string>();
  const out: string[] = [];

  let m: RegExpExecArray | null;
  while ((m = hrefRe.exec(html)) !== null) {
    const href = m[1];
    if (!href) continue;

    let abs: URL;
    try {
      abs = new URL(href, pageUrl);
    } catch {
      continue;
    }

    if (abs.protocol !== 'https:' && abs.protocol !== 'http:') continue;
    if (abs.hostname.toLowerCase() !== ARTICLE_HOST) continue;
    if (!ARTICLE_PATH_RE.test(abs.pathname)) continue;

    abs.hash = '';
    abs.search = '';
    const normalized = normalizeUrl(abs.toString());
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(abs.toString());
    if (out.length >= maxItems) break;
  }

  return out;
}

async function fetchArticle(url: string): Promise<NormalizedEntry | null> {
  validateUrlForFetch(url);
  const resp = await fetchWithTimeout(
    url,
    { headers: { 'User-Agent': 'NewsHub/0.1' } },
    { timeoutMs: 10_000, retries: 1 },
  );
  const html = await resp.text();

  const title = getTitle(html);
  if (!title) return null;

  const publishedAt = parseDateToIso(
    getMetaContent(html, 'article:published_time')
      ?? getMetaContent(html, 'og:pubdate')
      ?? getMetaContent(html, 'parsely-pub-date'),
  );

  const snippet = stripHtml(
    getMetaContent(html, 'og:description')
      ?? getMetaContent(html, 'description')
      ?? '',
  ).slice(0, 500);

  const normalizedUrl = normalizeUrl(url);
  const [itemKey, titleHash] = await Promise.all([
    hashHex(normalizedUrl),
    hashHex(title),
  ]);

  return {
    sourceUrl: url,
    normalizedUrl,
    itemKey,
    titleHe: title,
    publishedAt,
    snippetHe: snippet || null,
    titleHash,
    dateConfidence: publishedAt ? 'high' : 'low',
  };
}

/**
 * Fetch ynet news listing page and parse linked article pages.
 * Returns up to `maxItems` normalized entries.
 */
export async function fetchHtmlNews(pageUrl: string, maxItems: number): Promise<NormalizedEntry[]> {
  validateUrlForFetch(pageUrl);
  const pageResp = await fetchWithTimeout(
    pageUrl,
    { headers: { 'User-Agent': 'NewsHub/0.1' } },
    { timeoutMs: 10_000, retries: 1 },
  );
  const pageHtml = await pageResp.text();
  const articleUrls = extractArticleUrls(pageUrl, pageHtml, maxItems);

  const entries: NormalizedEntry[] = [];
  for (const articleUrl of articleUrls) {
    const parsed = await fetchArticle(articleUrl);
    if (parsed) entries.push(parsed);
  }

  return entries;
}
