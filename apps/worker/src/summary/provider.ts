/**
 * SummaryProvider interface — abstraction over LLM/MT/rule-based backends.
 *
 * Implementations:
 *  - GeminiProvider   (primary — free tier, no billing required)
 *  - ClaudeProvider   (secondary — high quality, requires credits)
 *  - RuleBasedProvider(last resort — no external calls, deterministic)
 *
 * Providers receive `env` directly so they can read their own API keys
 * without constructor injection.
 */

import type { Env } from '../index';

export interface SummaryItem {
  itemId: string;
  titleHe: string;
  sourceId: string;
  publishedAt: string | null;
}

export interface SummaryProvider {
  /** Stable identifier used in logs and error_events. */
  readonly name: string;

  /**
   * Generate a Russian summary in the mandatory 5-section format:
   *   Заголовок: …
   *   Что произошло: …
   *   Почему важно: …
   *   Что дальше: …
   *   Источники: …
   *
   * Throws on unrecoverable failure so ProviderChain can try the next provider.
   */
  generate(items: SummaryItem[], riskLevel: string, env: Env): Promise<string>;
}
