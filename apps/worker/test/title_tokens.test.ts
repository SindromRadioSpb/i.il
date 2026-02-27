import { describe, expect, it } from 'vitest';
import { tokenize, jaccardSimilarity } from '../src/normalize/title_tokens';

// ---------------------------------------------------------------------------
// tokenize
// ---------------------------------------------------------------------------
describe('tokenize', () => {
  it('returns a Set of tokens', () => {
    const tokens = tokenize('ביבי נפגש עם מנהיגים');
    expect(tokens).toBeInstanceOf(Set);
  });

  it('removes Hebrew stopwords', () => {
    const tokens = tokenize('ביבי נפגש עם מנהיגים');
    // 'עם' is a stopword
    expect(tokens.has('עם')).toBe(false);
    expect(tokens.has('ביבי')).toBe(true);
    expect(tokens.has('נפגש')).toBe(true);
    expect(tokens.has('מנהיגים')).toBe(true);
  });

  it('removes tokens shorter than 2 characters', () => {
    const tokens = tokenize('ו א ב שריפה');
    expect(tokens.has('ו')).toBe(false);
    expect(tokens.has('א')).toBe(false);
    expect(tokens.has('שריפה')).toBe(true);
  });

  it('splits on punctuation and whitespace', () => {
    const tokens = tokenize('שריפה, בחיפה: פצועים');
    expect(tokens.has('שריפה')).toBe(true);
    expect(tokens.has('בחיפה')).toBe(true);
    expect(tokens.has('פצועים')).toBe(true);
  });

  it('lowercases Latin tokens', () => {
    const tokens = tokenize('Hamas מקבלת נשק');
    expect(tokens.has('hamas')).toBe(true);
  });

  it('keeps numeric tokens of length >= 2', () => {
    const tokens = tokenize('100 הרוגים ב-1948');
    expect(tokens.has('100')).toBe(true);
    expect(tokens.has('1948')).toBe(true);
  });

  it('returns empty set for all-stopword input', () => {
    const tokens = tokenize('של את אל עם כי');
    expect(tokens.size).toBe(0);
  });

  it('returns empty set for empty string', () => {
    expect(tokenize('').size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// jaccardSimilarity
// ---------------------------------------------------------------------------
describe('jaccardSimilarity', () => {
  it('returns 1 for identical sets', () => {
    const a = new Set(['a', 'b', 'c']);
    expect(jaccardSimilarity(a, a)).toBe(1);
  });

  it('returns 1 for two empty sets', () => {
    expect(jaccardSimilarity(new Set(), new Set())).toBe(1);
  });

  it('returns 0 for disjoint sets', () => {
    const a = new Set(['שריפה', 'חיפה']);
    const b = new Set(['רעידה', 'תורכיה']);
    expect(jaccardSimilarity(a, b)).toBe(0);
  });

  it('returns 0 when one set is empty', () => {
    const a = new Set(['a', 'b']);
    expect(jaccardSimilarity(a, new Set())).toBe(0);
    expect(jaccardSimilarity(new Set(), a)).toBe(0);
  });

  it('computes correct value for partial overlap', () => {
    // |A∩B|=2, |A∪B|=4 → 0.5
    const a = new Set(['x', 'y', 'z']);
    const b = new Set(['x', 'y', 'w']);
    expect(jaccardSimilarity(a, b)).toBeCloseTo(2 / 4, 5);
  });

  it('is symmetric', () => {
    const a = new Set(['ביבי', 'נפגש', 'מנהיגים']);
    const b = new Set(['ביבי', 'נפגש', 'נשיאים', 'אירופאים']);
    expect(jaccardSimilarity(a, b)).toBeCloseTo(jaccardSimilarity(b, a), 10);
  });

  it('real Hebrew match scenario', () => {
    // "ביבי נפגש עם מנהיגים" vs "ביבי נפגש עם נשיאים"
    // tokens (after stopword removal): {ביבי, נפגש, מנהיגים} vs {ביבי, נפגש, נשיאים}
    // |A∩B|=2, |A∪B|=4 → 0.5
    const a = tokenize('ביבי נפגש עם מנהיגים');
    const b = tokenize('ביבי נפגש עם נשיאים');
    expect(jaccardSimilarity(a, b)).toBeGreaterThan(0.25); // above clustering threshold
  });

  it('real Hebrew non-match scenario', () => {
    const a = tokenize('שריפה בחיפה');
    const b = tokenize('רעידת אדמה בתורכיה');
    expect(jaccardSimilarity(a, b)).toBe(0);
  });
});
