interface RunRow {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  sources_ok: number;
  sources_failed: number;
  items_found: number;
  items_new: number;
  stories_new: number;
  stories_updated: number;
  published_web: number;
  published_fb: number;
  errors_total: number;
  duration_ms: number;
}

/**
 * Fetch the most recent run record from D1.
 * Catches all DB errors and returns null rather than exposing error details.
 */
export async function getLastRun(db: D1Database): Promise<object | null> {
  try {
    const row = await db
      .prepare(
        `SELECT run_id, started_at, finished_at, status,
                sources_ok, sources_failed, items_found, items_new,
                stories_new, stories_updated, published_web, published_fb,
                errors_total, duration_ms
         FROM runs
         ORDER BY started_at DESC
         LIMIT 1`,
      )
      .first<RunRow>();

    if (!row) return null;

    return {
      run_id: row.run_id,
      started_at: row.started_at,
      finished_at: row.finished_at,
      status: row.status,
      counters: {
        sources_ok: row.sources_ok,
        sources_failed: row.sources_failed,
        items_found: row.items_found,
        items_new: row.items_new,
        stories_new: row.stories_new,
        stories_updated: row.stories_updated,
        published_web: row.published_web,
        published_fb: row.published_fb,
        errors_total: row.errors_total,
      },
      duration_ms: row.duration_ms,
    };
  } catch {
    return null;
  }
}
