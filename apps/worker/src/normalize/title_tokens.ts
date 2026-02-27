/**
 * Hebrew-safe title tokenization for story clustering.
 * Splits on non-letter characters, removes stopwords, discards short tokens.
 */

// Common Hebrew function words that carry no topic signal.
const HE_STOPWORDS = new Set([
  'של', 'את', 'אל', 'עם', 'כי', 'על', 'זה', 'זו', 'זאת',
  'הם', 'הן', 'היה', 'היו', 'הוא', 'היא', 'לא', 'גם', 'אבל',
  'כן', 'אם', 'כבר', 'רק', 'עוד', 'כל', 'כלל', 'אחד', 'אחת',
  'שני', 'שתי', 'מה', 'מי', 'לו', 'לה', 'להם', 'לנו', 'לי',
  'כך', 'אז', 'יש', 'אין', 'אחרי', 'לפני', 'בין', 'תחת',
  'מתוך', 'כנגד', 'בגלל', 'כדי', 'כמו', 'אחרת', 'או', 'שוב',
  'עכשיו', 'יותר', 'פחות', 'הכל', 'ממנו', 'ממנה', 'אלה', 'אלו',
  'כבר', 'רק', 'עוד', 'בה', 'בהם', 'בנו', 'בי', 'ומה',
  'ועל', 'ואל', 'ועם', 'ולא', 'וגם', 'אנחנו', 'אתם', 'אתן',
]);

/**
 * Tokenize a Hebrew (or mixed) title into a set of meaningful tokens.
 * - Splits on whitespace and punctuation (Unicode-aware).
 * - Lowercases (primarily affects mixed Hebrew+Latin titles).
 * - Drops tokens shorter than 2 characters.
 * - Drops Hebrew stopwords.
 */
export function tokenize(title: string): Set<string> {
  // \u05D0-\u05EA = Hebrew alphabet block
  const parts = title.split(/[^\u05D0-\u05EAa-zA-Z0-9]+/);
  const tokens = new Set<string>();
  for (const raw of parts) {
    const t = raw.trim().toLowerCase();
    if (t.length < 2) continue;
    if (HE_STOPWORDS.has(t)) continue;
    tokens.add(t);
  }
  return tokens;
}

/**
 * Jaccard similarity between two token sets: |A∩B| / |A∪B|.
 * Returns 0 when one set is empty; returns 1 when both are empty.
 */
export function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  if (a.size === 0 || b.size === 0) return 0;

  let intersection = 0;
  for (const token of a) {
    if (b.has(token)) intersection++;
  }
  const union = a.size + b.size - intersection;
  return intersection / union;
}
