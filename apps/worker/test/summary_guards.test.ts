import { describe, expect, it } from 'vitest';
import {
  guardLength,
  guardForbiddenWords,
  guardNumbers,
  guardHighRisk,
} from '../src/summary/guards';

// ---------------------------------------------------------------------------
// guardLength
// ---------------------------------------------------------------------------
describe('guardLength', () => {
  it('ok when within range', () => {
    const body = 'А'.repeat(500);
    expect(guardLength(body, 400, 700).ok).toBe(true);
  });

  it('ok at exact minimum', () => {
    expect(guardLength('А'.repeat(400), 400, 700).ok).toBe(true);
  });

  it('ok at exact maximum', () => {
    expect(guardLength('А'.repeat(700), 400, 700).ok).toBe(true);
  });

  it('fails when too short', () => {
    const result = guardLength('А'.repeat(100), 400, 700);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain('too_short');
  });

  it('fails when too long', () => {
    const result = guardLength('А'.repeat(800), 400, 700);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain('too_long');
  });
});

// ---------------------------------------------------------------------------
// guardForbiddenWords
// ---------------------------------------------------------------------------
describe('guardForbiddenWords', () => {
  it('ok for clean text', () => {
    expect(guardForbiddenWords('Правительство обсудило бюджет.').ok).toBe(true);
  });

  it('fails on "ужас"', () => {
    const result = guardForbiddenWords('Это настоящий ужас для города.');
    expect(result.ok).toBe(false);
    expect(result.reason).toContain('ужас');
  });

  it('fails on "кошмар"', () => {
    expect(guardForbiddenWords('Настоящий кошмар.').ok).toBe(false);
  });

  it('fails on "шок"', () => {
    expect(guardForbiddenWords('Рынки в шоке.').ok).toBe(false);
  });

  it('fails on "сенсация"', () => {
    expect(guardForbiddenWords('Это сенсация!').ok).toBe(false);
  });

  it('is case-insensitive', () => {
    expect(guardForbiddenWords('УЖАС').ok).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// guardNumbers
// ---------------------------------------------------------------------------
describe('guardNumbers', () => {
  it('ok when all source numbers appear in generated text', () => {
    const titles = ['3 ракеты выпущены', '50% граждан'];
    const generated = 'ЦАХАЛ сообщил о 3 ракетах. Поддержка составила 50%.';
    expect(guardNumbers(titles, generated).ok).toBe(true);
  });

  it('fails when a number is missing', () => {
    const titles = ['100 пострадавших'];
    const generated = 'Пострадало несколько человек.';
    const result = guardNumbers(titles, generated);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain('100');
  });

  it('ok when source titles have no numbers', () => {
    const titles = ['Переговоры продолжаются', 'Ситуация сложная'];
    const generated = 'Стороны продолжают переговоры.';
    expect(guardNumbers(titles, generated).ok).toBe(true);
  });

  it('handles percentage values', () => {
    const titles = ['Рост 3.5%'];
    const generated = 'Экономика выросла на 3.5%.';
    expect(guardNumbers(titles, generated).ok).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// guardHighRisk
// ---------------------------------------------------------------------------
describe('guardHighRisk', () => {
  it('ok for low risk without attribution', () => {
    expect(guardHighRisk('Правительство обсудило бюджет.', 'low').ok).toBe(true);
  });

  it('ok for medium risk without attribution', () => {
    expect(guardHighRisk('Суд рассмотрел дело.', 'medium').ok).toBe(true);
  });

  it('fails for high risk without "по данным источников"', () => {
    const result = guardHighRisk('Произошёл теракт в центре города.', 'high');
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('high_risk_requires_attribution');
  });

  it('ok for high risk with "по данным источников"', () => {
    const body = 'По данным источников, произошёл теракт в центре города.';
    expect(guardHighRisk(body, 'high').ok).toBe(true);
  });

  it('attribution check is case-insensitive', () => {
    const body = 'По Данным Источников, в городе введён комендантский час.';
    expect(guardHighRisk(body, 'high').ok).toBe(true);
  });
});
