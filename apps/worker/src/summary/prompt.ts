/**
 * Shared prompt builders used by all LLM-based providers.
 * Kept here so Claude/Gemini/future providers stay in sync.
 */

import type { SummaryItem } from './provider';

/** Build the system prompt with editorial rules and mandatory format. */
export function buildSystemPrompt(riskLevel: string): string {
  const highRiskNote =
    riskLevel === 'high'
      ? '\n- ОБЯЗАТЕЛЬНО: добавь "по данным источников" в раздел "Что произошло".'
      : '';

  return `Ты аналитик по Ближнему Востоку и профессиональный русскоязычный редактор.

Сделай экспертный пересказ израильских новостей с иврита на русский.
Текст должен звучать как сдержанный экспертный комментарий: без эмоций, без кликбейта, с акцентом на факты и последствия для региона.

Используй СТРОГО следующую структуру (все 5 разделов обязательны):

Заголовок: <одна фактическая строка>
Что произошло: <1-2 предложения>
Почему важно: <1 предложение>
Что дальше: <1 предложение или "Ожидается обновление.">
Источники: <названия источников через запятую>

Правила:
- Язык: только русский (кроме названий источников)
- Длина тела (без строки "Источники"): 400-700 символов
- Сохраняй все числа, проценты и суммы точно
- Используй точно: ЦАХАЛ, ШАБАК, Кнессет, Тель-Авив, Иерусалим, Хайфа
- Тон: нейтральный и фактологичный
- Запрещенные слова: ужас, кошмар, шок, сенсация, скандал${highRiskNote}`;
}

/** Build the user message listing Hebrew news items. */
export function buildUserMessage(items: SummaryItem[]): string {
  const list = items.map((it, i) => `${i + 1}. [${it.sourceId}] ${it.titleHe}`).join('\n');
  return `Новостные заголовки на иврите:\n${list}`;
}
