/**
 * Claude API integration for Russian summary generation.
 * Uses direct fetch (no SDK) for Cloudflare Workers compatibility.
 */

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

interface AnthropicResponse {
  content: { type: string; text: string }[];
}

export interface SummaryItem {
  titleHe: string;
  sourceId: string;
  publishedAt: string | null;
}

/** Build the system prompt with editorial rules and mandatory format. */
function buildSystemPrompt(riskLevel: string): string {
  const highRiskNote =
    riskLevel === 'high'
      ? '\n- ОБЯЗАТЕЛЬНО: добавь "по данным источников" в раздел "Что произошло".'
      : '';

  return `Ты профессиональный редактор русскоязычных новостей, пересказывающий израильские новости с иврита.

Создай пересказ на русском, используя СТРОГО следующую структуру (все 5 разделов обязательны):

Заголовок: <одна фактическая строка>
Что произошло: <1–2 предложения>
Почему важно: <1 предложение>
Что дальше: <1 предложение или "Ожидается обновление.">
Источники: <названия источников через запятую>

Правила:
- Язык: только русский (кроме названий источников)
- Длина тела (без строки "Источники"): 400–700 символов
- Сохраняй все числа, проценты и суммы точно
- Используй точно: ЦАХАЛ, ШАБАК, Кнессет, Тель-Авив, Иерусалим, Хайфа
- Тон: нейтральный и фактологичный, без эмоций
- Запрещённые слова: ужас, кошмар, шок, сенсация, скандал${highRiskNote}`;
}

/**
 * Call the Anthropic Messages API and return the generated text.
 * Throws on HTTP error or missing text content in the response.
 */
export async function callClaude(
  apiKey: string,
  model: string,
  items: SummaryItem[],
  riskLevel: string,
): Promise<string> {
  const itemList = items
    .map((it, i) => `${i + 1}. [${it.sourceId}] ${it.titleHe}`)
    .join('\n');

  const res = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': ANTHROPIC_VERSION,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 600,
      system: buildSystemPrompt(riskLevel),
      messages: [{ role: 'user', content: `Новостные заголовки на иврите:\n${itemList}` }],
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => 'unknown');
    throw new Error(`Claude API ${res.status}: ${errText}`);
  }

  const data = (await res.json()) as AnthropicResponse;
  const text = data.content.find(c => c.type === 'text')?.text;
  if (!text) throw new Error('Claude returned no text content');
  return text;
}
