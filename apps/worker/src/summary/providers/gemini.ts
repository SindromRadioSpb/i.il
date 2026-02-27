import type { Env } from '../../index';
import type { SummaryItem, SummaryProvider } from '../provider';
import { buildSystemPrompt, buildUserMessage } from '../prompt';

const GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models';

interface GeminiResponse {
  candidates?: {
    content?: {
      parts?: { text?: string }[];
    };
  }[];
}

export class GeminiProvider implements SummaryProvider {
  readonly name = 'gemini';

  async generate(items: SummaryItem[], riskLevel: string, env: Env): Promise<string> {
    const apiKey = env.GEMINI_API_KEY;
    if (!apiKey) throw new Error('GEMINI_API_KEY not configured');

    const model = env.GEMINI_MODEL ?? 'gemini-2.0-flash';
    const url = `${GEMINI_API_BASE}/${model}:generateContent?key=${apiKey}`;

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: buildSystemPrompt(riskLevel) }] },
        contents: [{ role: 'user', parts: [{ text: buildUserMessage(items) }] }],
        generationConfig: { maxOutputTokens: 600, temperature: 0.3 },
      }),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => 'unknown');
      throw new Error(`Gemini API ${res.status}: ${errText}`);
    }

    const data = (await res.json()) as GeminiResponse;
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) throw new Error('Gemini returned no text content');
    return text;
  }
}
