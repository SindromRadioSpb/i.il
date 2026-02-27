import { describe, expect, it, vi } from 'vitest';
import { ProviderChain, buildChain } from '../src/summary/provider_chain';
import type { SummaryProvider } from '../src/summary/provider';
import type { Env } from '../src/index';

const ITEMS = [
  { itemId: 'i1', titleHe: 'כותרת ראשית', sourceId: 'ynet_main', publishedAt: null },
];

const VALID_TEXT = [
  'Заголовок: Тест',
  'Что произошло: Событие произошло.',
  'Почему важно: Это важно.',
  'Что дальше: Ожидается обновление.',
  'Источники: Ynet',
].join('\n');

function makeProvider(name: string, result: string | Error): SummaryProvider {
  return {
    name,
    generate: vi.fn().mockImplementation(() =>
      result instanceof Error ? Promise.reject(result) : Promise.resolve(result),
    ),
  };
}

const FAKE_ENV = {} as Env;

// ---------------------------------------------------------------------------
describe('ProviderChain — success', () => {
  it('returns result from first provider when it succeeds', async () => {
    const chain = new ProviderChain([
      makeProvider('primary', VALID_TEXT),
      makeProvider('fallback', 'should not be called'),
    ]);
    const result = await chain.generate(ITEMS, 'low', FAKE_ENV);
    expect(result.text).toBe(VALID_TEXT);
    expect(result.providerName).toBe('primary');
  });

  it('falls back to second provider when first throws', async () => {
    const chain = new ProviderChain([
      makeProvider('primary', new Error('API error')),
      makeProvider('fallback', VALID_TEXT),
    ]);
    const result = await chain.generate(ITEMS, 'low', FAKE_ENV);
    expect(result.providerName).toBe('fallback');
    expect(result.text).toBe(VALID_TEXT);
  });

  it('falls back to third provider when first two throw', async () => {
    const chain = new ProviderChain([
      makeProvider('p1', new Error('fail1')),
      makeProvider('p2', new Error('fail2')),
      makeProvider('p3', VALID_TEXT),
    ]);
    const result = await chain.generate(ITEMS, 'low', FAKE_ENV);
    expect(result.providerName).toBe('p3');
  });
});

// ---------------------------------------------------------------------------
describe('ProviderChain — all fail', () => {
  it('throws when all providers fail', async () => {
    const chain = new ProviderChain([
      makeProvider('p1', new Error('fail1')),
      makeProvider('p2', new Error('fail2')),
    ]);
    await expect(chain.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow('All providers failed');
  });

  it('error message includes all provider names', async () => {
    const chain = new ProviderChain([
      makeProvider('gemini', new Error('quota')),
      makeProvider('claude', new Error('no credits')),
    ]);
    await expect(chain.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow('gemini');
  });
});

// ---------------------------------------------------------------------------
describe('ProviderChain — length', () => {
  it('reports correct number of providers', () => {
    const chain = new ProviderChain([makeProvider('a', ''), makeProvider('b', '')]);
    expect(chain.length).toBe(2);
  });

  it('empty chain throws immediately', async () => {
    const chain = new ProviderChain([]);
    await expect(chain.generate(ITEMS, 'low', FAKE_ENV)).rejects.toThrow('All providers failed');
  });
});

// ---------------------------------------------------------------------------
describe('buildChain', () => {
  it('includes gemini when GEMINI_API_KEY is set', () => {
    const env = { GEMINI_API_KEY: 'key', SUMMARY_PROVIDERS: 'gemini' } as unknown as Env;
    expect(buildChain(env).length).toBe(1);
  });

  it('excludes gemini when GEMINI_API_KEY is missing', () => {
    const env = { SUMMARY_PROVIDERS: 'gemini' } as unknown as Env;
    expect(buildChain(env).length).toBe(0);
  });

  it('always includes rule_based regardless of keys', () => {
    const env = { SUMMARY_PROVIDERS: 'rule_based' } as unknown as Env;
    expect(buildChain(env).length).toBe(1);
  });

  it('uses default order when SUMMARY_PROVIDERS is not set', () => {
    // No keys → only rule_based from default order gemini,claude,rule_based
    const env = {} as Env;
    expect(buildChain(env).length).toBe(1); // rule_based only
  });

  it('includes all three when all keys are set', () => {
    const env = {
      GEMINI_API_KEY: 'g-key',
      ANTHROPIC_API_KEY: 'a-key',
      SUMMARY_PROVIDERS: 'gemini,claude,rule_based',
    } as unknown as Env;
    expect(buildChain(env).length).toBe(3);
  });
});
