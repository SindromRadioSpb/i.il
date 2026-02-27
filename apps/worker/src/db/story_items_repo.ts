/**
 * Attach an item to a story.
 *
 * INSERT OR IGNORE ensures idempotency: re-runs that see already-clustered
 * items produce no side-effects.
 *
 * Returns true if the item was actually attached (i.e., it was new to this story).
 */
export async function attachItem(
  db: D1Database,
  storyId: string,
  itemId: string,
  addedAt: string,
): Promise<boolean> {
  const result = await db
    .prepare(
      `INSERT OR IGNORE INTO story_items (story_id, item_id, added_at, rank)
       VALUES (?, ?, ?, 0)`,
    )
    .bind(storyId, itemId, addedAt)
    .run();

  return (result.meta?.changes ?? 0) > 0;
}
