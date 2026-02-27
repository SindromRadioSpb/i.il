export interface RunCounters {
  sourcesOk: number;
  sourcesFailed: number;
  itemsFound: number;
  itemsNew: number;
  storiesNew: number;
  storiesUpdated: number;
  publishedWeb: number;
  publishedFb: number;
  errorsTotal: number;
}

/** Insert a new run row with status='in_progress'. */
export async function startRun(db: D1Database, runId: string): Promise<void> {
  const now = new Date().toISOString();
  await db
    .prepare(
      `INSERT INTO runs (run_id, started_at, status)
       VALUES (?, ?, 'in_progress')`,
    )
    .bind(runId, now)
    .run();
}

/** Update the run row with final counters and computed status. */
export async function finishRun(
  db: D1Database,
  runId: string,
  startedAtMs: number,
  counters: RunCounters,
): Promise<void> {
  const finishedAt = new Date().toISOString();
  const durationMs = Date.now() - startedAtMs;

  const status =
    counters.sourcesFailed === 0
      ? 'success'
      : counters.sourcesOk > 0
        ? 'partial_failure'
        : 'failure';

  await db
    .prepare(
      `UPDATE runs
       SET finished_at     = ?,
           status          = ?,
           sources_ok      = ?,
           sources_failed  = ?,
           items_found     = ?,
           items_new       = ?,
           stories_new     = ?,
           stories_updated = ?,
           published_web   = ?,
           published_fb    = ?,
           errors_total    = ?,
           duration_ms     = ?
       WHERE run_id = ?`,
    )
    .bind(
      finishedAt,
      status,
      counters.sourcesOk,
      counters.sourcesFailed,
      counters.itemsFound,
      counters.itemsNew,
      counters.storiesNew,
      counters.storiesUpdated,
      counters.publishedWeb,
      counters.publishedFb,
      counters.errorsTotal,
      durationMs,
      runId,
    )
    .run();
}
