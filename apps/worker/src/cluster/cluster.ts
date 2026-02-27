import type { NormalizedEntry } from '../ingest/types';
import { tokenize, jaccardSimilarity } from '../normalize/title_tokens';
import {
  findRecentStories,
  createStory,
  updateStoryLastUpdate,
} from '../db/stories_repo';
import { attachItem } from '../db/story_items_repo';

/** Look back 24 hours for candidate stories. */
const CLUSTER_WINDOW_MS = 24 * 60 * 60 * 1000;

/** Minimum Jaccard similarity required to attach to an existing story. */
const SIMILARITY_THRESHOLD = 0.25;

export interface ClusterCounters {
  storiesNew: number;
  storiesUpdated: number;
}

type ClusterItem = Pick<NormalizedEntry, 'itemKey' | 'titleHe' | 'publishedAt'>;

/**
 * Cluster a list of newly-ingested items into stories.
 *
 * Algorithm (per item):
 *  1. Tokenize item title.
 *  2. Scan candidate stories (from last 24 h) for highest Jaccard similarity.
 *  3. If similarity ≥ THRESHOLD → attach item; bump story.last_update_at.
 *  4. Otherwise → create a new story, attach item.
 *  5. In-memory candidate map is updated after each attach so that items
 *     within the same run can match a story created by an earlier item.
 *
 * All DB writes are INSERT OR IGNORE / idempotent, so re-running is safe.
 */
export async function clusterNewItems(
  db: D1Database,
  items: ClusterItem[],
): Promise<ClusterCounters> {
  if (items.length === 0) return { storiesNew: 0, storiesUpdated: 0 };

  const candidates = await findRecentStories(db, CLUSTER_WINDOW_MS);

  // In-memory map: storyId → token set (updated as items are clustered).
  const candidateTokens = new Map<string, Set<string>>(
    candidates.map(c => [c.storyId, tokenize(c.titleHe)]),
  );

  const counters: ClusterCounters = { storiesNew: 0, storiesUpdated: 0 };
  const now = new Date().toISOString();

  for (const item of items) {
    const itemTokens = tokenize(item.titleHe);

    // Find best-matching story above threshold.
    let bestStoryId: string | null = null;
    let bestScore = SIMILARITY_THRESHOLD; // must exceed (not just equal)

    for (const [storyId, storyTokens] of candidateTokens) {
      const score = jaccardSimilarity(itemTokens, storyTokens);
      if (score > bestScore) {
        bestScore = score;
        bestStoryId = storyId;
      }
    }

    if (bestStoryId !== null) {
      const attached = await attachItem(db, bestStoryId, item.itemKey, now);
      if (attached) {
        await updateStoryLastUpdate(db, bestStoryId, now);
        // Expand candidate tokens so subsequent items in this run can match.
        const existing = candidateTokens.get(bestStoryId);
        if (existing !== undefined) {
          for (const t of itemTokens) existing.add(t);
        }
        counters.storiesUpdated++;
      }
    } else {
      const newStoryId = crypto.randomUUID();
      const startAt = item.publishedAt ?? now;
      await createStory(db, newStoryId, startAt);
      await attachItem(db, newStoryId, item.itemKey, now);
      // Register new story so items later in this run can match it.
      candidateTokens.set(newStoryId, new Set(itemTokens));
      counters.storiesNew++;
    }
  }

  return counters;
}
