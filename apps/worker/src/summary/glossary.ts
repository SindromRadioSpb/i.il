/**
 * Post-generation glossary normalization.
 * Enforces consistent Russian spellings of Hebrew institutions, cities, and terms.
 * Applied to generated text AFTER Claude output to catch any inconsistencies.
 *
 * City rules use stem-based matching so declined forms are also normalized
 * (e.g. хайфы → Хайфы, тель авива → Тель-Авива).
 */

type Replacer = string | ((...args: string[]) => string);

// [pattern, replacement] — all patterns are case-insensitive.
// For function replacers, rest args[0] = full match, args[1] = first capture group.
const RULES: Array<[RegExp, Replacer]> = [
  // Institutions — undeclined in Russian news style
  [/цахал/gi, 'ЦАХАЛ'],
  [/шабак/gi, 'ШАБАК'],
  // Кнессет — capture any Cyrillic case suffix (Кнессета, Кнессете, …)
  [/кнес+ет([а-яё]*)/gi, (...a: string[]) => 'Кнессет' + (a[1] ?? '')],
  // Cities — match stem + optional Cyrillic suffix so declined forms are also fixed
  [/тель[\s-]?авив([а-яё]*)/gi, (...a: string[]) => 'Тель-Авив' + (a[1] ?? '')],
  [/иерусалим([а-яё]*)/gi, (...a: string[]) => 'Иерусалим' + (a[1] ?? '')],
  // хайф + at least one Cyrillic letter covers хайфа/хайфы/хайфе/хайфу/хайфой
  [/хайф([а-яё]+)/gi, (...a: string[]) => 'Хайф' + (a[1] ?? '')],
];

/** Apply glossary normalization rules to a generated Russian text. */
export function applyGlossary(text: string): string {
  let result = text;
  for (const [pattern, replacement] of RULES) {
    // Double cast so TS picks a single overload; runtime is correct because
    // JS replace() accepts both string and function as the second argument.
    result = result.replace(pattern, replacement as unknown as string);
  }
  return result;
}
