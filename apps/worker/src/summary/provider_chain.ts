/**
 * ProviderChain — tries each SummaryProvider in order until one succeeds.
 *
 * buildChain() constructs the chain from available env keys using the
 * provider order defined in SUMMARY_PROVIDERS (default: gemini,claude,rule_based).
 * Providers without a configured API key are silently skipped.
 */

import type { Env } from '../index';
import type { SummaryItem, SummaryProvider } from './provider';
import { GeminiProvider } from './providers/gemini';
import { ClaudeProvider } from './providers/claude';
import { GoogleTranslateProvider } from './providers/google_translate';
import { RuleBasedProvider } from './providers/rule_based';

export interface ChainResult {
  text: string;
  providerName: string;
}

export class ProviderChain {
  private readonly providers: SummaryProvider[];

  constructor(providers: SummaryProvider[]) {
    this.providers = providers;
  }

  get length(): number {
    return this.providers.length;
  }

  async generate(items: SummaryItem[], riskLevel: string, env: Env): Promise<ChainResult> {
    const errors: string[] = [];

    for (const provider of this.providers) {
      try {
        const text = await provider.generate(items, riskLevel, env);
        return { text, providerName: provider.name };
      } catch (err) {
        errors.push(`${provider.name}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    throw new Error(`All providers failed — ${errors.join(' | ')}`);
  }
}

const DEFAULT_ORDER = 'gemini,claude,google_translate,rule_based';

/**
 * Build a ProviderChain from the environment.
 * Only providers with their required key present are included
 * (except rule_based which needs no key).
 */
export function buildChain(env: Env): ProviderChain {
  const order = (env.SUMMARY_PROVIDERS ?? DEFAULT_ORDER)
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);

  const providers: SummaryProvider[] = [];

  for (const name of order) {
    switch (name) {
      case 'gemini':
        if (env.GEMINI_API_KEY) providers.push(new GeminiProvider());
        break;
      case 'claude':
        if (env.ANTHROPIC_API_KEY) providers.push(new ClaudeProvider());
        break;
      case 'google_translate':
        providers.push(new GoogleTranslateProvider());
        break;
      case 'rule_based':
        providers.push(new RuleBasedProvider());
        break;
    }
  }

  return new ProviderChain(providers);
}
