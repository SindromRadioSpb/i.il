/** A parsed, normalized entry ready for DB upsert. */
export interface NormalizedEntry {
  sourceUrl: string;        // original URL from feed
  normalizedUrl: string;    // tracking-stripped, lowercased
  itemKey: string;          // sha256(normalizedUrl) — primary dedupe key
  titleHe: string;          // headline text (Hebrew)
  publishedAt: string | null; // ISO8601 UTC or null
  snippetHe: string | null; // stripped description, max 500 chars
  titleHash: string;        // sha256(titleHe)
  dateConfidence: 'high' | 'low';
}
