/**
 * Parsing and formatting of the mandatory 5-section Russian summary structure.
 *
 * Expected Claude output format:
 *   Заголовок: <headline>
 *   Что произошло: <1–2 sentences>
 *   Почему важно: <1 sentence>
 *   Что дальше: <1 sentence>
 *   Источники: <source names>
 */

export interface ParsedSummary {
  title: string;
  whatHappened: string;
  whyImportant: string;
  whatsNext: string;
  sources: string;
}

const SECTIONS = [
  { key: 'Заголовок', field: 'title' },
  { key: 'Что произошло', field: 'whatHappened' },
  { key: 'Почему важно', field: 'whyImportant' },
  { key: 'Что дальше', field: 'whatsNext' },
  { key: 'Источники', field: 'sources' },
] as const;

/**
 * Parse Claude output into structured sections.
 * Each section starts with "Key: value" on its own line.
 * Multi-line continuation is supported for section content.
 * Returns null if any required section is missing or has an empty value.
 */
export function parseSections(text: string): ParsedSummary | null {
  const lines = text.split('\n');
  const result: Partial<ParsedSummary> = {};

  for (let sIdx = 0; sIdx < SECTIONS.length; sIdx++) {
    const { key, field } = SECTIONS[sIdx]!;
    const nextKey = sIdx + 1 < SECTIONS.length ? SECTIONS[sIdx + 1]!.key : null;

    // Find the line that begins this section
    const startIdx = lines.findIndex(l => l.trim().startsWith(key + ':'));
    if (startIdx === -1) return null;

    // Find where this section ends (start of next section or EOF)
    let endIdx = lines.length;
    if (nextKey !== null) {
      const ni = lines.findIndex((l, i) => i > startIdx && l.trim().startsWith(nextKey + ':'));
      if (ni !== -1) endIdx = ni;
    }

    // Collect the value: inline text after "Key:" + any continuation lines
    const firstLine = lines[startIdx]!.trim().slice(key.length + 1).trim();
    const continuations = lines
      .slice(startIdx + 1, endIdx)
      .map(l => l.trim())
      .filter(Boolean)
      .join(' ');

    const value = continuations ? `${firstLine} ${continuations}`.trim() : firstLine;
    if (!value) return null;

    (result as Record<string, string>)[field] = value;
  }

  return result as ParsedSummary;
}

/**
 * The body text used for character-length checks (excludes the Источники line).
 */
export function formatBody(parsed: ParsedSummary): string {
  return [
    `Что произошло: ${parsed.whatHappened}`,
    `Почему важно: ${parsed.whyImportant}`,
    `Что дальше: ${parsed.whatsNext}`,
  ].join('\n');
}

/**
 * Full display text stored in summary_ru (title + body + sources).
 */
export function formatFull(parsed: ParsedSummary): string {
  return [
    parsed.title,
    '',
    `Что произошло: ${parsed.whatHappened}`,
    `Почему важно: ${parsed.whyImportant}`,
    `Что дальше: ${parsed.whatsNext}`,
    `Источники: ${parsed.sources}`,
  ].join('\n');
}
