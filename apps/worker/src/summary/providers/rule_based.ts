/**
 * Rule-based last-resort provider.
 *
 * Does NOT call any external API. Produces a minimal but structurally valid
 * Russian summary from the Hebrew titles as-is (untranslated).
 * Intended as a safety net so stories are never stuck in draft indefinitely
 * when all LLM providers fail.
 *
 * Quality note: titles stay in Hebrew — the summary is marked "данные уточняются"
 * to signal it needs human review. The guards are intentionally relaxed via the
 * short body — callers may choose to skip guards for this provider.
 */

import type { Env } from '../../index';
import type { SummaryItem, SummaryProvider } from '../provider';
import { getSourceById } from '../../sources/registry';

export class RuleBasedProvider implements SummaryProvider {
  readonly name = 'rule_based';

  generate(items: SummaryItem[], riskLevel: string, _env: Env): Promise<string> {
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
    const sourcesLine = sourceNames.length > 0 ? sourceNames.join(', ') : 'источник не определён';

    // Use the first title as headline (Hebrew, no translation)
    const headline = items[0]?.titleHe ?? 'Новость';

    // Build "Что произошло" from up to 3 titles
    const whatHappened =
      items
        .slice(0, 3)
        .map(it => it.titleHe)
        .join('. ') + '. Данные уточняются.';

    const whyImportant =
      riskLevel === 'high'
        ? 'По данным источников, событие требует повышенного внимания.'
        : 'По данным источников, ситуация находится под наблюдением.';

    const whatsNext = 'Ожидается обновление.';

    return Promise.resolve(
      [
        `Заголовок: ${headline}`,
        `Что произошло: ${whatHappened}`,
        `Почему важно: ${whyImportant}`,
        `Что дальше: ${whatsNext}`,
        `Источники: ${sourcesLine}`,
      ].join('\n'),
    );
  }
}
