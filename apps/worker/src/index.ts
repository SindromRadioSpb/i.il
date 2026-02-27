import type { ExportedHandler } from '@cloudflare/workers-types';
import { route } from './router';

export interface Env {
  DB: D1Database;
  CRON_ENABLED: string;
  FB_POSTING_ENABLED: string;
  ADMIN_ENABLED: string;
  CRON_INTERVAL_MIN: string;
  MAX_NEW_ITEMS_PER_RUN: string;
  SUMMARY_TARGET_MIN: string;
  SUMMARY_TARGET_MAX: string;
}

const handler: ExportedHandler<Env> = {
  // Let TypeScript infer param types from ExportedHandler<Env> to stay compatible
  // with whatever Request/ExecutionContext variant workers-types exports.
  async fetch(request, env, ctx) {
    return route(request, env, ctx);
  },

  // Cron handler is guarded by CRON_ENABLED (see router/cron module later).
  async scheduled(_controller, env, _ctx) {
    if (env.CRON_ENABLED !== 'true') return;
    // Placeholder: implemented in PATCH-05 and later.
    // _ctx.waitUntil(runCronIngest(env));
  },
};

export default handler;
