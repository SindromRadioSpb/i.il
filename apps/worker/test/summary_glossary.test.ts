import { describe, expect, it } from 'vitest';
import { applyGlossary } from '../src/summary/glossary';

describe('applyGlossary', () => {
  it('normalizes цахал → ЦАХАЛ (lower)', () => {
    expect(applyGlossary('Силы цахал провели операцию')).toBe('Силы ЦАХАЛ провели операцию');
  });

  it('normalizes ЦАХАЛ → ЦАХАЛ (already correct)', () => {
    expect(applyGlossary('ЦАХАЛ сообщил')).toBe('ЦАХАЛ сообщил');
  });

  it('normalizes шабак → ШАБАК', () => {
    expect(applyGlossary('По данным шабак')).toBe('По данным ШАБАК');
  });

  it('normalizes кнесет → Кнессет', () => {
    expect(applyGlossary('заседание кнесета')).toBe('заседание Кнессета');
  });

  it('normalizes кнессет → Кнессет (double-с variant)', () => {
    expect(applyGlossary('заседание кнессета')).toBe('заседание Кнессета');
  });

  it('normalizes Тель Авив (space) → Тель-Авив', () => {
    expect(applyGlossary('жители тель авива')).toBe('жители Тель-Авива');
  });

  it('normalizes тель-авив (hyphen, lower) → Тель-Авив', () => {
    expect(applyGlossary('в тель-авиве')).toBe('в Тель-Авиве');
  });

  it('normalizes иерусалим → Иерусалим', () => {
    expect(applyGlossary('премьер иерусалима')).toBe('премьер Иерусалима');
  });

  it('normalizes хайфа → Хайфа', () => {
    expect(applyGlossary('порт хайфы')).toBe('порт Хайфы');
  });

  it('does not mutate unrelated text', () => {
    const text = 'Правительство обсудило бюджет на 2026 год.';
    expect(applyGlossary(text)).toBe(text);
  });
});
