import type { Env } from '../../index';
import type { SummaryItem, SummaryProvider } from '../provider';
import { buildSystemPrompt, buildUserMessage } from '../prompt';

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

interface AnthropicResponse {
  content: { type: string; text: string }[];
}

export class ClaudeProvider implements SummaryProvider {
  readonly name = 'claude';

  async generate(items: SummaryItem[], riskLevel: string, env: Env): Promise<string> {
    const apiKey = env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error('ANTHROPIC_API_KEY not configured');

    const model = env.ANTHROPIC_MODEL ?? 'claude-haiku-4-5-20251001';

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
        messages: [{ role: 'user', content: buildUserMessage(items) }],
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
}
