import { describe, expect, it } from 'vitest';
import { parseSections, formatBody, formatFull } from '../src/summary/format';

const VALID_TEXT = `Заголовок: В Тель-Авиве произошло землетрясение
Что произошло: Землетрясение магнитудой 4.5 произошло ранним утром.
Почему важно: Это первое ощутимое землетрясение за последнее десятилетие.
Что дальше: Сейсмологи продолжают мониторинг ситуации.
Источники: Ynet, Mako`;

describe('parseSections — valid input', () => {
  it('returns ParsedSummary for valid 5-section text', () => {
    const result = parseSections(VALID_TEXT);
    expect(result).not.toBeNull();
    expect(result!.title).toBe('В Тель-Авиве произошло землетрясение');
    expect(result!.whatHappened).toContain('4.5');
    expect(result!.whyImportant).toContain('десятилетие');
    expect(result!.whatsNext).toContain('мониторинг');
    expect(result!.sources).toBe('Ynet, Mako');
  });

  it('handles leading/trailing whitespace in section values', () => {
    const text = `Заголовок:   Заголовок с пробелами
Что произошло: Событие.
Почему важно: Важность.
Что дальше: Ожидается обновление.
Источники: Haaretz`;
    const result = parseSections(text);
    expect(result).not.toBeNull();
    expect(result!.title).toBe('Заголовок с пробелами');
  });

  it('joins multi-line content within a section', () => {
    const text = `Заголовок: Заголовок
Что произошло: Первое предложение.
Второе предложение той же секции.
Почему важно: Важность.
Что дальше: Ожидается обновление.
Источники: Ynet`;
    const result = parseSections(text);
    expect(result).not.toBeNull();
    expect(result!.whatHappened).toContain('Первое предложение');
    expect(result!.whatHappened).toContain('Второе предложение');
  });
});

describe('parseSections — invalid input', () => {
  it('returns null when Заголовок section is missing', () => {
    const text = `Что произошло: Событие.
Почему важно: Важность.
Что дальше: Ожидается обновление.
Источники: Ynet`;
    expect(parseSections(text)).toBeNull();
  });

  it('returns null when Что произошло section is missing', () => {
    const text = `Заголовок: Заголовок
Почему важно: Важность.
Что дальше: Ожидается обновление.
Источники: Ynet`;
    expect(parseSections(text)).toBeNull();
  });

  it('returns null when section value is empty', () => {
    const text = `Заголовок:
Что произошло: Событие.
Почему важно: Важность.
Что дальше: Ожидается обновление.
Источники: Ynet`;
    expect(parseSections(text)).toBeNull();
  });

  it('returns null for completely empty string', () => {
    expect(parseSections('')).toBeNull();
  });
});

describe('formatBody', () => {
  it('includes the three body sections but not Источники', () => {
    const parsed = parseSections(VALID_TEXT)!;
    const body = formatBody(parsed);
    expect(body).toContain('Что произошло:');
    expect(body).toContain('Почему важно:');
    expect(body).toContain('Что дальше:');
    expect(body).not.toContain('Источники:');
    expect(body).not.toContain(parsed.title);
  });
});

describe('formatFull', () => {
  it('includes all five sections with title on first line', () => {
    const parsed = parseSections(VALID_TEXT)!;
    const full = formatFull(parsed);
    const lines = full.split('\n');
    expect(lines[0]).toBe(parsed.title);
    expect(full).toContain('Что произошло:');
    expect(full).toContain('Почему важно:');
    expect(full).toContain('Что дальше:');
    expect(full).toContain('Источники:');
  });
});
