import type { NormalizedEntry } from '../ingest/types';

/**
 * Upsert a batch of normalized entries into the items table.
 * Uses INSERT OR IGNORE with item_key as the dedup key (sha256 of normalizedUrl).
 * item_id is set equal to item_key for deterministic, idempotent inserts.
 *
 * Returns the count of rows that were actually inserted (new items only).
 */
export async function upsertItems(
  db: D1Database,
  entries: NormalizedEntry[],
  sourceId: string,
): Promise<{ found: number; inserted: number; newKeys: string[] }> {
  if (entries.length === 0) return { found: 0, inserted: 0, newKeys: [] };

  const now = new Date().toISOString();

  const stmts = entries.map(e =>
    db
      .prepare(
        `INSERT OR IGNORE INTO items
           (item_id, source_id, source_url, normalized_url, item_key,
            title_he, published_at, updated_at, date_confidence,
            snippet_he, title_hash, ingested_at, status)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')`,
      )
      .bind(
        e.itemKey,        // item_id  = item_key (deterministic, idempotent)
        sourceId,
        e.sourceUrl,
        e.normalizedUrl,
        e.itemKey,        // item_key = sha256(normalizedUrl)
        e.titleHe,
        e.publishedAt,
        e.publishedAt,    // updated_at mirrors published_at on insert
        e.dateConfidence,
        e.snippetHe,
        e.titleHash,
        now,
      ),
  );

  const results = await db.batch(stmts);
  const newKeys: string[] = [];
  for (let i = 0; i < results.length; i++) {
    if ((results[i]?.meta?.changes ?? 0) > 0) {
      newKeys.push(entries[i]!.itemKey);
    }
  }
  return { found: entries.length, inserted: newKeys.length, newKeys };
}
