import { describe, expect, it } from 'vitest';
import {
  getEnabledSources,
  getAllSources,
  getSourceById,
} from '../src/sources/registry';

describe('source registry', () => {
  it('getAllSources returns all sources', () => {
    const all = getAllSources();
    expect(all.length).toBeGreaterThan(0);
  });

  it('getEnabledSources returns only enabled sources', () => {
    const all = getAllSources();
    const enabled = getEnabledSources();
    const disabledCount = all.filter(s => !s.enabled).length;
    expect(enabled.length).toBe(all.length - disabledCount);
    expect(enabled.every(s => s.enabled)).toBe(true);
  });

  it('ynet_rss_index is disabled', () => {
    const src = getSourceById('ynet_rss_index');
    expect(src).toBeDefined();
    expect(src?.enabled).toBe(false);
  });

  it('getSourceById returns correct source', () => {
    const src = getSourceById('ynet_main');
    expect(src).toBeDefined();
    expect(src?.name).toMatch(/ynet/);
    expect(src?.type).toBe('rss');
    expect(src?.lang).toBe('he');
  });

  it('getSourceById returns undefined for unknown id', () => {
    expect(getSourceById('does_not_exist')).toBeUndefined();
  });

  it('all sources have required fields', () => {
    for (const src of getAllSources()) {
      expect(typeof src.id).toBe('string');
      expect(src.id.length).toBeGreaterThan(0);
      expect(typeof src.url).toBe('string');
      expect(src.url).toMatch(/^https?:\/\//);
      expect(['rss', 'sitemap', 'html']).toContain(src.type);
    }
  });

  it('all rss sources have throttle settings', () => {
    for (const src of getAllSources().filter(s => s.type === 'rss')) {
      expect(src.throttle).toBeDefined();
      expect(src.throttle?.max_items_per_run).toBeGreaterThan(0);
      expect(src.throttle?.min_interval_sec).toBeGreaterThan(0);
    }
  });
});
