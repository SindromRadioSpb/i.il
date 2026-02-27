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
  // Optional — set via `wrangler secret put ANTHROPIC_API_KEY`
  ANTHROPIC_API_KEY?: string;
  // Default: claude-haiku-4-5-20251001
  ANTHROPIC_MODEL?: string;
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
