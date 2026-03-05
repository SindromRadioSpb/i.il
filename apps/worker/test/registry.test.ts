import { describe, expect, it } from 'vitest';
import {
  getEnabledSources,
  getAllSources,
  getSourceById,
} from '../src/sources/registry';

describe('source registry (single ynet page)', () => {
  it('contains exactly one source', () => {
    const all = getAllSources();
    expect(all).toHaveLength(1);
  });

  it('the source is enabled and html type', () => {
    const enabled = getEnabledSources();
    expect(enabled).toHaveLength(1);
    expect(enabled[0]?.id).toBe('ynet_news_page');
    expect(enabled[0]?.type).toBe('html');
    expect(enabled[0]?.url).toBe('https://www.ynet.co.il/news');
  });

  it('getSourceById returns ynet_news_page', () => {
    const src = getSourceById('ynet_news_page');
    expect(src).toBeDefined();
    expect(src?.name).toContain('ynet');
    expect(src?.lang).toBe('he');
  });

  it('returns undefined for unknown source id', () => {
    expect(getSourceById('does_not_exist')).toBeUndefined();
  });

  it('source has throttle settings', () => {
    const src = getSourceById('ynet_news_page');
    expect(src?.throttle).toBeDefined();
    expect(src?.throttle?.max_items_per_run).toBeGreaterThan(0);
    expect(src?.throttle?.min_interval_sec).toBeGreaterThan(0);
  });
});
