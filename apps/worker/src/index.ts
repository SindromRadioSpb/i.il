import type { ExportedHandler } from '@cloudflare/workers-types';
import { route } from './router';
import { runIngest } from './cron/ingest';

export interface Env {
  DB: D1Database;
  CRON_ENABLED: string;
  FB_POSTING_ENABLED: string;
  ADMIN_ENABLED: string;
  CRON_INTERVAL_MIN: string;
  MAX_NEW_ITEMS_PER_RUN: string;
  SUMMARY_TARGET_MIN: string;
  SUMMARY_TARGET_MAX: string;
  // Secrets — set via `wrangler secret put <KEY>`
  ANTHROPIC_API_KEY?: string;
  GEMINI_API_KEY?: string;
  FB_PAGE_ACCESS_TOKEN?: string;
  FB_PAGE_TOKEN?: string;        // alias — secret was set with this name
  // Model overrides (defaults set in wrangler.toml vars)
  ANTHROPIC_MODEL?: string;
  GEMINI_MODEL?: string;
  // Comma-separated provider order (default: gemini,claude,rule_based)
  SUMMARY_PROVIDERS?: string;
  // Facebook crossposting
  FB_PAGE_ID?: string;
  PUBLIC_SITE_BASE_URL?: string;
  // Cron budget — max wall-clock ms per run (default: 25000)
  CRON_BUDGET_MS?: string;
  SERVICE_ENV?: string;
}

const handler: ExportedHandler<Env> = {
  // Let TypeScript infer param types from ExportedHandler<Env> to stay compatible
  // with whatever Request/ExecutionContext variant workers-types exports.
  async fetch(request, env, ctx) {
    return route(request, env, ctx);
  },

  // Cron handler — guarded by CRON_ENABLED flag.
  async scheduled(_controller, env, ctx) {
    if (env.CRON_ENABLED !== 'true') return;
    ctx.waitUntil(runIngest(env));
  },
};

export default handler;
