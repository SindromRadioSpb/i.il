// Synced from sources/registry.yaml (authoritative documentation).
// When adding or removing sources, update both files.
import { SourceSchema, type Source } from './types';

const RAW: unknown[] = [
  {
    id: 'ynet_main',
    name: 'ynet (ראשי)',
    type: 'rss',
    url: 'https://www.ynet.co.il/Integration/StoryRss1854.xml',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 10, max_items_per_run: 25 },
    category_hints: ['politics', 'security', 'economy', 'society', 'tech', 'health', 'culture', 'sport'],
  },
  {
    id: 'ynet_rss_index',
    name: 'ynet RSS index (directory)',
    type: 'html',
    url: 'https://z.ynet.co.il/short/content/RSS/index.html',
    lang: 'he',
    enabled: false,
    throttle: { min_interval_sec: 20, max_items_per_run: 10 },
    category_hints: ['other'],
  },
  {
    id: 'haaretz_rss_directory',
    name: 'Haaretz RSS directory',
    type: 'rss',
    url: 'https://www.haaretz.co.il/misc/rss',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 15 },
    category_hints: ['politics', 'security', 'economy', 'society', 'culture'],
  },
  {
    id: 'israelhayom_rss',
    name: 'ישראל היום (RSS)',
    type: 'rss',
    url: 'https://www.israelhayom.co.il/rss',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 20 },
    category_hints: ['politics', 'security', 'economy', 'society', 'culture', 'sport'],
  },
  {
    id: 'mako_news',
    name: 'mako חדשות (RSS)',
    type: 'rss',
    url: 'https://rcs.mako.co.il/rss/31750a2610f26110VgnVCM1000005201000aRCRD.xml',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 20 },
    category_hints: ['politics', 'security', 'economy', 'society', 'culture', 'sport', 'weather'],
  },
  {
    id: 'mako_breaking',
    name: 'mako מבזקים (RSS)',
    type: 'rss',
    url: 'https://storage.googleapis.com/mako-sitemaps/rssFlash.xml',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 10, max_items_per_run: 25 },
    category_hints: ['politics', 'security', 'economy', 'society', 'other'],
  },
  {
    id: 'mako_military',
    name: 'mako צבא וביטחון (RSS)',
    type: 'rss',
    url: 'https://rcs.mako.co.il/rss/news-military.xml',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 15 },
    category_hints: ['security'],
  },
  {
    id: 'walla_news',
    name: 'וואלה! חדשות (RSS)',
    type: 'rss',
    url: 'https://rss.walla.co.il/feed/22',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 20 },
    category_hints: ['politics', 'security', 'economy', 'society', 'culture', 'sport', 'weather'],
  },
  {
    id: 'maariv_breaking',
    name: 'מעריב מבזקים (RSS)',
    type: 'rss',
    url: 'https://www.maariv.co.il/Rss/RssFeedsMivzakiChadashot',
    lang: 'he',
    enabled: true,
    throttle: { min_interval_sec: 15, max_items_per_run: 20 },
    category_hints: ['politics', 'security', 'economy', 'society', 'culture', 'sport'],
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
