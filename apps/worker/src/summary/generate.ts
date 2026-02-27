/**
 * Legacy export kept for backward-compat with existing tests.
 * New code should use SummaryProvider / ProviderChain instead.
 */

export type { SummaryItem } from './provider';
export { ClaudeProvider } from './providers/claude';

// Re-export callClaude as a standalone function for tests that use it directly.
import type { SummaryItem } from './provider';
import { ClaudeProvider } from './providers/claude';
import type { Env } from '../index';

/**
 * @deprecated Use ClaudeProvider or ProviderChain instead.
 */
export async function callClaude(
  apiKey: string,
  model: string,
  items: SummaryItem[],
  riskLevel: string,
): Promise<string> {
  const provider = new ClaudeProvider();
  const fakeEnv = { ANTHROPIC_API_KEY: apiKey, ANTHROPIC_MODEL: model } as Env;
  return provider.generate(items, riskLevel, fakeEnv);
}
