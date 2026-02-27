/**
 * Pre-publication guards for generated Russian summaries.
 * Each guard returns { ok: true } or { ok: false, reason: string }.
 */

export interface GuardResult {
  ok: boolean;
  reason?: string;
}

/** Verify the summary body length is within the allowed character range. */
export function guardLength(body: string, min: number, max: number): GuardResult {
  const len = body.length;
  if (len < min) return { ok: false, reason: `too_short:${len}<${min}` };
  if (len > max) return { ok: false, reason: `too_long:${len}>${max}` };
  return { ok: true };
}

const FORBIDDEN_WORDS = ['ужас', 'кошмар', 'шок', 'сенсация', 'скандал века'];

/** Detect forbidden sensational language. */
export function guardForbiddenWords(text: string): GuardResult {
  const lower = text.toLowerCase();
  for (const word of FORBIDDEN_WORDS) {
    if (lower.includes(word)) {
      return { ok: false, reason: `forbidden_word:${word}` };
    }
  }
  return { ok: true };
}

/** Extract all numeric sequences (including those with % or decimal separators). */
function extractNumbers(text: string): string[] {
  return text.match(/\d+(?:[.,]\d+)?%?/g) ?? [];
}

/**
 * Verify that every number found in the source Hebrew titles also appears
 * in the generated Russian text. Numbers must be preserved exactly.
 */
export function guardNumbers(sourceTitles: string[], generatedText: string): GuardResult {
  const sourceNums = new Set(sourceTitles.flatMap(extractNumbers));
  if (sourceNums.size === 0) return { ok: true };

  const genNums = new Set(extractNumbers(generatedText));
  const missing = [...sourceNums].filter(n => !genNums.has(n));
  if (missing.length > 0) {
    return { ok: false, reason: `missing_numbers:${missing.join(',')}` };
  }
  return { ok: true };
}

/**
 * For high-risk stories (casualties, terror, emergencies), the body must
 * contain the attribution phrase "по данным источников".
 */
export function guardHighRisk(body: string, riskLevel: string): GuardResult {
  if (riskLevel !== 'high') return { ok: true };
  if (!body.toLowerCase().includes('по данным источников')) {
    return { ok: false, reason: 'high_risk_requires_attribution' };
  }
  return { ok: true };
}
