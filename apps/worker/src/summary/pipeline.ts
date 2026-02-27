/**
 * Summary generation pipeline orchestrator.
 *
 * For each draft story:
 *  1. Fetch its items.
 *  2. Compute a content hash; skip if already generated for this exact content.
 *  3. Run ProviderChain (Gemini → Claude → rule_based).
 *  4. Apply glossary, parse sections, run guards.
 *  5. Persist (story → published, publications row created).
 */

import type { Env } from '../index';
import { buildChain } from './provider_chain';
import { applyGlossary } from './glossary';
import { parseSections, formatBody, formatFull } from './format';
import { guardLength, guardForbiddenWords, guardNumbers, guardHighRisk } from './guards';
import { hashHex } from '../normalize/hash';
import {
  getStoriesNeedingSummary,
  getStoryItemsForSummary,
  updateStorySummary,
} from '../db/stories_repo';
import { recordError } from '../db/errors_repo';

const MAX_SUMMARIES_PER_RUN = 5;

export interface SummaryCounters {
  attempted: number;
  published: number;
  skipped: number;
  failed: number;
}

export async function runSummaryPipeline(env: Env, runId: string): Promise<SummaryCounters> {
  const db = env.DB;
  const targetMin = parseInt(env.SUMMARY_TARGET_MIN ?? '400', 10) || 400;
  const targetMax = parseInt(env.SUMMARY_TARGET_MAX ?? '700', 10) || 700;

  const counters: SummaryCounters = { attempted: 0, published: 0, skipped: 0, failed: 0 };

  const chain = buildChain(env);
  if (chain.length === 0) return counters; // no providers configured

  const stories = await getStoriesNeedingSummary(db, MAX_SUMMARIES_PER_RUN);

  for (const story of stories) {
    counters.attempted++;
    try {
      const items = await getStoryItemsForSummary(db, story.storyId);
      if (items.length === 0) {
        counters.skipped++;
        continue;
      }

      // Memoization: skip if this exact content was already summarized.
      const hashInput =
        [...items.map(i => i.itemId)].sort().join(',') + ':' + story.riskLevel;
      const newHash = await hashHex(hashInput);
      if (story.summaryHash === newHash) {
        counters.skipped++;
        continue;
      }

      // Generate via chain
      const { text: raw, providerName } = await chain.generate(items, story.riskLevel, env);
      const glossarized = applyGlossary(raw);
      const parsed = parseSections(glossarized);
      if (!parsed) {
        await recordError(
          db,
          runId,
          'summary',
          null,
          story.storyId,
          new Error(`format_parse_failed [${providerName}]`),
        );
        counters.failed++;
        continue;
      }

      const body = formatBody(parsed);
      const fullText = formatFull(parsed);

      // Guards (rule_based provider may produce short bodies — allow it through)
      const isRuleBased = providerName === 'rule_based';
      const guardResults = [
        isRuleBased ? { ok: true } : guardLength(body, targetMin, targetMax),
        guardForbiddenWords(fullText),
        guardNumbers(items.map(i => i.titleHe), fullText),
        guardHighRisk(body, story.riskLevel),
      ];
      const firstFailed = guardResults.find(g => !g.ok);
      if (firstFailed) {
        await recordError(
          db,
          runId,
          'summary',
          null,
          story.storyId,
          new Error(`${firstFailed.reason ?? 'guard_failed'} [${providerName}]`),
        );
        counters.failed++;
        continue;
      }

      await updateStorySummary(
        db,
        story.storyId,
        parsed.title,
        fullText,
        newHash,
        story.riskLevel,
      );
      counters.published++;
    } catch (err) {
      await recordError(db, runId, 'summary', null, story.storyId, err);
      counters.failed++;
    }
  }

  return counters;
}
