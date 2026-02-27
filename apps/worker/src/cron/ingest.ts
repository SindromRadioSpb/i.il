import type { Env } from '../index';
import { getEnabledSources } from '../sources/registry';
import { fetchRss } from '../ingest/rss';
import { upsertItems } from '../db/items_repo';
import { startRun, finishRun, type RunCounters } from '../db/runs_repo';
import { recordError } from '../db/errors_repo';
import { acquireLock, releaseLock } from './run_lock';
import { clusterNewItems } from '../cluster/cluster';
import { runSummaryPipeline } from '../summary/pipeline';

const LOCK_TTL_SEC = 300; // 5 minutes

/**
 * Main cron ingest orchestrator.
 *
 * Flow:
 *  1. Acquire distributed lease lock (prevents overlap if cron fires early).
 *  2. Record a new run in the runs table.
 *  3. For each enabled RSS source: fetch → normalize → upsert items → cluster new items.
 *  4. Finish run with final counters; release lock (in finally).
 *
 * Per-source errors are isolated: one bad feed does not stop the others.
 */
export async function runIngest(env: Env): Promise<void> {
  const runId = crypto.randomUUID();
  const startedAtMs = Date.now();
  const db = env.DB;
  const maxItemsPerRun = parseInt(env.MAX_NEW_ITEMS_PER_RUN || '25', 10) || 25;

  // Attempt to acquire the cron lock; bail if another run is in progress.
  const locked = await acquireLock(db, runId, LOCK_TTL_SEC);
  if (!locked) return;

  const counters: RunCounters = {
    sourcesOk: 0,
    sourcesFailed: 0,
    itemsFound: 0,
    itemsNew: 0,
    storiesNew: 0,
    storiesUpdated: 0,
    publishedWeb: 0,
    publishedFb: 0,
    errorsTotal: 0,
  };

  await startRun(db, runId);

  try {
    for (const source of getEnabledSources()) {
      if (source.type !== 'rss') continue;

      try {
        const maxItems = source.throttle?.max_items_per_run ?? maxItemsPerRun;
        const entries = await fetchRss(source.url, maxItems);
        const { found, inserted, newKeys } = await upsertItems(db, entries, source.id);
        counters.itemsFound += found;
        counters.itemsNew += inserted;

        // Cluster only items that were freshly inserted this run.
        if (newKeys.length > 0) {
          const newEntries = entries.filter(e => newKeys.includes(e.itemKey));
          const clusterResult = await clusterNewItems(db, newEntries);
          counters.storiesNew += clusterResult.storiesNew;
          counters.storiesUpdated += clusterResult.storiesUpdated;
        }

        counters.sourcesOk++;
      } catch (err) {
        counters.sourcesFailed++;
        counters.errorsTotal++;
        // Record but do not re-throw — other sources continue.
        await recordError(db, runId, 'ingest', source.id, null, err);
      }
    }
    // Generate Russian summaries for draft stories (only when API key is set).
    if (env.ANTHROPIC_API_KEY) {
      try {
        const summaryResult = await runSummaryPipeline(env, runId);
        counters.publishedWeb += summaryResult.published;
        counters.errorsTotal += summaryResult.failed;
      } catch (err) {
        counters.errorsTotal++;
        await recordError(db, runId, 'summary', null, null, err);
      }
    }
  } finally {
    await finishRun(db, runId, startedAtMs, counters);
    await releaseLock(db, runId);
  }
}
