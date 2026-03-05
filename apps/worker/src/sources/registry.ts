// Synced from sources/registry.yaml (authoritative documentation).
import { SourceSchema, type Source } from './types';

const RAW: unknown[] = [
  {
    id: 'ynet_news_page',
    name: 'ynet news page',
    type: 'html',
    url: 'https://www.ynet.co.il/news',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 10, max_items_per_run: 50 },
    category_hints: ['politics', 'security', 'economy', 'society', 'tech', 'health', 'culture', 'sport'],
  },
];

const _validated: Source[] = RAW.map(s => SourceSchema.parse(s));

export function getEnabledSources(): Source[] {
  return _validated.filter(s => s.enabled);
}

export function getAllSources(): Source[] {
  return _validated;
}

export function getSourceById(id: string): Source | undefined {
  return _validated.find(s => s.id === id);
}
