import type { Env } from '../index';
import { getEnabledSources } from '../sources/registry';
import { fetchRss } from '../ingest/rss';
import { upsertItems } from '../db/items_repo';
import { startRun, finishRun, type RunCounters } from '../db/runs_repo';
import { recordError } from '../db/errors_repo';
import { acquireLock, releaseLock } from './run_lock';
import { clusterNewItems } from '../cluster/cluster';
import { runSummaryPipeline } from '../summary/pipeline';
import { runFbCrosspost } from '../fb/post';
import { RunBudget } from './budget';

const LOCK_TTL_SEC = 300; // 5 minutes
const DEFAULT_BUDGET_MS = 25_000; // leave ~5s for finishRun + releaseLock

/**
 * Main cron ingest orchestrator.
 *
 * Flow:
 *  1. Acquire distributed lease lock (prevents overlap if cron fires early).
 *  2. Record a new run in the runs table.
 *  3. For each enabled RSS source (within time budget): fetch → normalize → upsert → cluster.
 *  4. Generate Russian summaries (within time budget).
 *  5. Post to Facebook (within time budget).
 *  6. Finish run with final counters; release lock (in finally).
 *
 * Per-source errors are isolated: one bad feed does not stop the others.
 * Budget checks prevent wall-clock overruns on Cloudflare Workers.
 */
export async function runIngest(env: Env): Promise<void> {
  const runId = crypto.randomUUID();
  const startedAtMs = Date.now();
  const db = env.DB;
  const maxItemsPerRun = parseInt(env.MAX_NEW_ITEMS_PER_RUN || '25', 10) || 25;
  const budgetMs = parseInt(env.CRON_BUDGET_MS ?? String(DEFAULT_BUDGET_MS), 10) || DEFAULT_BUDGET_MS;
  const budget = new RunBudget(budgetMs, startedAtMs);

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

      // Stop processing sources if we're running low on time.
      // Reserve 5s: RSS fetch timeout (up to 10s for the call itself) + clustering.
      if (!budget.hasTime(5_000)) break;

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

    // Generate Russian summaries for draft stories.
    // Reserve 8s: up to 5 LLM calls may each take several seconds.
    // buildChain() self-guards: returns empty chain when no API keys are configured.
    if (budget.hasTime(8_000)) {
      try {
        const summaryResult = await runSummaryPipeline(env, runId, budget);
        counters.publishedWeb += summaryResult.published;
        counters.errorsTotal += summaryResult.failed;
      } catch (err) {
        counters.errorsTotal++;
        await recordError(db, runId, 'summary', null, null, err);
      }
    }

    // Post published stories to Facebook.
    // Reserve 3s: up to 5 Graph API calls.
    if (env.FB_POSTING_ENABLED === 'true' && budget.hasTime(3_000)) {
      try {
        const fbResult = await runFbCrosspost(env, runId);
        counters.publishedFb += fbResult.posted;
        counters.errorsTotal += fbResult.failed;
      } catch (err) {
        counters.errorsTotal++;
        await recordError(db, runId, 'fb_crosspost', null, null, err);
      }
    }
  } finally {
    await finishRun(db, runId, startedAtMs, counters);
    await releaseLock(db, runId);
  }
}
