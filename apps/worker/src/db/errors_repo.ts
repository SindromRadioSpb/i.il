/**
 * Record a structured error event to the error_events table.
 * Errors are associated with a run and optionally a source or story.
 */
export async function recordError(
  db: D1Database,
  runId: string,
  phase: string,
  sourceId: string | null,
  storyId: string | null,
  err: unknown,
): Promise<void> {
  const eventId = crypto.randomUUID();
  const now = new Date().toISOString();
  const message = err instanceof Error ? err.message : String(err);
  const code =
    err instanceof Error &&
    typeof (err as unknown as Record<string, unknown>)['code'] === 'string'
      ? ((err as unknown as Record<string, unknown>)['code'] as string)
      : null;

  await db
    .prepare(
      `INSERT INTO error_events
         (event_id, run_id, phase, source_id, story_id, code, message, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(eventId, runId, phase, sourceId, storyId, code, message, now)
    .run();
}
