/**
 * GoogleTranslateProvider — translates Hebrew titles to Russian via
 * the unofficial Google Translate endpoint (no API key required).
 *
 * Used as a fallback when Gemini and Claude are unavailable.
 * Produces a structured 5-section summary from machine-translated titles.
 */

import type { Env } from '../../index';
import type { SummaryItem, SummaryProvider } from '../provider';
import { getSourceById } from '../../sources/registry';

const GT_BASE = 'https://translate.googleapis.com/translate_a/single';

async function translateText(text: string): Promise<string> {
  const params = new URLSearchParams({
    client: 'gtx',
    sl: 'he',
    tl: 'ru',
    dt: 't',
    q: text,
  });
  const res = await fetch(`${GT_BASE}?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Google Translate HTTP ${res.status}`);
  }
  // Response: [[[segment0_translated, segment0_source, ...], ...], null, "iw"]
  const data: unknown = await res.json();
  const outer = Array.isArray(data) ? (data as unknown[])[0] : undefined;
  if (!Array.isArray(outer)) {
    throw new Error('Google Translate: unexpected response shape');
  }
  const segments: string[] = [];
  for (const seg of outer as unknown[]) {
    if (Array.isArray(seg)) {
      const first = (seg as unknown[])[0];
      if (typeof first === 'string') segments.push(first);
    }
  }
  if (segments.length === 0) {
    throw new Error('Google Translate: no translation segments returned');
  }
  return segments.join('');
}

export class GoogleTranslateProvider implements SummaryProvider {
  readonly name = 'google_translate';

  async generate(items: SummaryItem[], riskLevel: string, _env: Env): Promise<string> {
    // Translate each headline sequentially (free tier: no concurrency limits but no key either)
    const translated: string[] = [];
    for (const item of items) {
      translated.push(await translateText(item.titleHe));
    }

    // Collect unique source names from registry
    const seenIds = new Set<string>();
    const sourceNames: string[] = [];
    for (const item of items) {
      if (!seenIds.has(item.sourceId)) {
        seenIds.add(item.sourceId);
        const src = getSourceById(item.sourceId);
        if (src) sourceNames.push(src.name);
      }
    }
    const sourcesLine =
      sourceNames.length > 0 ? sourceNames.join(', ') : 'источник не определён';

    const headline = translated[0] ?? 'Новость';
    const whatHappened = translated.slice(0, 3).join('. ') + '.';
    const whyImportant =
      riskLevel === 'high'
        ? 'По данным источников, событие требует повышенного внимания.'
        : 'По данным источников, ситуация находится под наблюдением.';
    const whatsNext = 'Ожидается обновление.';

    return [
      `Заголовок: ${headline}`,
      `Что произошло: ${whatHappened}`,
      `Почему важно: ${whyImportant}`,
      `Что дальше: ${whatsNext}`,
      `Источники: ${sourcesLine}`,
    ].join('\n');
  }
}
