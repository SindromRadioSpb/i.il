import { XMLParser } from 'fast-xml-parser';
import { normalizeUrl, validateUrlForFetch } from '../normalize/url';
import { hashHex } from '../normalize/hash';
import { fetchWithTimeout } from '../net/fetch_with_timeout';
import type { NormalizedEntry } from './types';

const PARSER = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  // Ensure these are always arrays even with a single element
  isArray: (name: string) => name === 'item' || name === 'entry',
  trimValues: true,
});

// Strip HTML tags and normalize whitespace.
function stripHtml(html: string): string {
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#?\w+;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Parse RFC 2822 / ISO 8601 date to ISO 8601 UTC string.
function parseDateToIso(raw: unknown): string | null {
  if (typeof raw !== 'string' || !raw.trim()) return null;
  try {
    const d = new Date(raw.trim());
    return isNaN(d.getTime()) ? null : d.toISOString();
  } catch {
    return null;
  }
}

// Safe string extraction from fast-xml-parser value (string | {#text: string} | number).
function strVal(v: unknown): string {
  if (typeof v === 'string') return v;
  if (typeof v === 'number') return String(v);
  if (v !== null && typeof v === 'object') {
    const t = (v as Record<string, unknown>)['#text'];
    if (typeof t === 'string') return t;
    if (typeof t === 'number') return String(t);
  }
  return '';
}

type XmlObj = Record<string, unknown>;

function extractItems(parsed: XmlObj): unknown[] {
  // RSS 2.0
  const rss = parsed['rss'];
  if (rss && typeof rss === 'object') {
    const channel = (rss as XmlObj)['channel'];
    if (channel && typeof channel === 'object') {
      const items = (channel as XmlObj)['item'];
      if (Array.isArray(items)) return items;
      if (items) return [items];
    }
  }
  // Atom
  const feed = parsed['feed'];
  if (feed && typeof feed === 'object') {
    const entries = (feed as XmlObj)['entry'];
    if (Array.isArray(entries)) return entries;
    if (entries) return [entries];
  }
  return [];
}

function extractLink(item: XmlObj): string {
  // RSS 2.0: <link>
  const link = item['link'];
  const linkStr = strVal(link);
  if (linkStr && (linkStr.startsWith('http://') || linkStr.startsWith('https://'))) {
    return linkStr;
  }
  // Atom: <link href="..."/>
  if (link && typeof link === 'object') {
    const href = strVal((link as XmlObj)['@_href']);
    if (href) return href;
  }
  // Fallback: <guid> if it looks like a URL
  const guid = item['guid'];
  const guidStr = strVal(guid);
  if (guidStr && (guidStr.startsWith('http://') || guidStr.startsWith('https://'))) {
    return guidStr;
  }
  return '';
}

function extractTitle(item: XmlObj): string {
  return stripHtml(strVal(item['title']));
}

function extractSnippet(item: XmlObj): string {
  const raw =
    strVal(item['description']) ||
    strVal(item['summary']) ||
    strVal((item['content:encoded'] as unknown) ?? item['content'] ?? '');
  return stripHtml(raw).slice(0, 500);
}

function extractPubDate(item: XmlObj): unknown {
  return item['pubDate'] ?? item['published'] ?? item['updated'] ?? item['dc:date'];
}

/**
 * Fetch and parse an RSS 2.0 or Atom feed.
 * SSRF-guarded: blocks private IPs and non-http(s) schemes.
 * Returns up to `maxItems` normalized entries.
 */
export async function fetchRss(url: string, maxItems: number): Promise<NormalizedEntry[]> {
  validateUrlForFetch(url);

  const resp = await fetchWithTimeout(
    url,
    { headers: { 'User-Agent': 'NewsHub/0.1' } },
    { timeoutMs: 10_000, retries: 1 },
  );

  const text = await resp.text();
  const parsed = PARSER.parse(text) as XmlObj;
  const rawItems = extractItems(parsed).slice(0, maxItems);

  const entries: NormalizedEntry[] = [];

  for (const raw of rawItems) {
    const item = raw as XmlObj;

    const rawUrl = extractLink(item);
    if (!rawUrl) continue;

    const title = extractTitle(item);
    if (!title) continue;

    const normalizedUrl = normalizeUrl(rawUrl);
    const snippet = extractSnippet(item);
    const publishedAt = parseDateToIso(extractPubDate(item));

    const [itemKey, titleHash] = await Promise.all([
      hashHex(normalizedUrl),
      hashHex(title),
    ]);

    entries.push({
      sourceUrl: rawUrl,
      normalizedUrl,
      itemKey,
      titleHe: title,
      publishedAt,
      snippetHe: snippet || null,
      titleHash,
      dateConfidence: publishedAt ? 'high' : 'low',
    });
  }

  return entries;
}
