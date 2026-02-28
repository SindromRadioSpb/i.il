import type { ExecutionContext } from '@cloudflare/workers-types';
import type { Env } from './index';
import { getLastRun, getTopFailingSources } from './api/health';
import { getRecentRuns, getRunErrors, getDraftStories, getDraftCounts, holdStory, releaseStory } from './api/admin';
import { getFeed } from './api/feed';
import { getStory } from './api/story';
import { runIngest } from './cron/ingest';

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    },
  });
}

// Admin routes use restricted CORS (ops-page origin only, not wildcard).
// allowedOrigin comes from PUBLIC_SITE_BASE_URL env var; if empty no CORS header is emitted.
function adminJson(data: unknown, status = 200, allowedOrigin?: string): Response {
  const headers: Record<string, string> = {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  };
  if (allowedOrigin) {
    headers['access-control-allow-origin'] = allowedOrigin;
    headers['access-control-allow-headers'] = 'x-admin-token';
  }
  return new Response(JSON.stringify(data), { status, headers });
}

function err(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
  return json({ ok: false, error: { code, message, details } }, status);
}

export async function route(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  try {
    const url = new URL(request.url);
    const { pathname } = url;

    // GET /api/v1/health
    if (request.method === 'GET' && pathname === '/api/v1/health') {
      const [lastRun, topFailingSources] = await Promise.all([
        getLastRun(env.DB),
        getTopFailingSources(env.DB),
      ]);
      return json({
        ok: true,
        service: {
          name: 'news-hub',
          version: '0.1.0',
          env: env.SERVICE_ENV ?? 'prod',
          now_utc: new Date().toISOString(),
        },
        last_run: lastRun,
        top_failing_sources: topFailingSources,
      });
    }

    // Admin routes — gated by ADMIN_ENABLED and optional ADMIN_SECRET_TOKEN
    if (pathname.startsWith('/api/v1/admin/')) {
      const corsOrigin = env.PUBLIC_SITE_BASE_URL || undefined;

      // CORS preflight — respond with the ops-page origin (or no CORS if not configured)
      if (request.method === 'OPTIONS') {
        return new Response(null, {
          status: 204,
          headers: corsOrigin
            ? {
                'access-control-allow-origin': corsOrigin,
                'access-control-allow-methods': 'GET, POST, OPTIONS',
                'access-control-allow-headers': 'x-admin-token',
                'access-control-max-age': '86400',
              }
            : {},
        });
      }

      if (env.ADMIN_ENABLED !== 'true') {
        return adminJson(
          { ok: false, error: { code: 'forbidden', message: 'Admin endpoints are disabled', details: {} } },
          403,
          corsOrigin,
        );
      }

      // Token check — only enforced when ADMIN_SECRET_TOKEN secret is configured
      if (env.ADMIN_SECRET_TOKEN) {
        const provided = request.headers.get('x-admin-token');
        if (provided !== env.ADMIN_SECRET_TOKEN) {
          return adminJson(
            { ok: false, error: { code: 'forbidden', message: 'Invalid or missing admin token', details: {} } },
            403,
            corsOrigin,
          );
        }
      }

      // GET /api/v1/admin/runs
      if (request.method === 'GET' && pathname === '/api/v1/admin/runs') {
        const runs = await getRecentRuns(env.DB);
        return adminJson({ ok: true, data: { runs } }, 200, corsOrigin);
      }

      // GET /api/v1/admin/errors?run_id=X
      if (request.method === 'GET' && pathname === '/api/v1/admin/errors') {
        const runId = url.searchParams.get('run_id');
        if (!runId) {
          return adminJson(
            { ok: false, error: { code: 'invalid_request', message: 'run_id query param required', details: {} } },
            400,
            corsOrigin,
          );
        }
        const errors = await getRunErrors(env.DB, runId);
        return adminJson({ ok: true, data: { errors } }, 200, corsOrigin);
      }

      // GET /api/v1/admin/drafts — draft stories pending editorial review
      if (request.method === 'GET' && pathname === '/api/v1/admin/drafts') {
        const [drafts, counts] = await Promise.all([
          getDraftStories(env.DB),
          getDraftCounts(env.DB),
        ]);
        return adminJson({ ok: true, data: { drafts, counts } }, 200, corsOrigin);
      }

      // POST /api/v1/admin/story/:id/hold — pause auto-publishing for a draft
      const holdMatch = /^\/api\/v1\/admin\/story\/([^/]+)\/hold$/.exec(pathname);
      if (request.method === 'POST' && holdMatch !== null) {
        const storyId = holdMatch[1]!;
        const updated = await holdStory(env.DB, storyId);
        if (!updated) {
          return adminJson(
            { ok: false, error: { code: 'not_found', message: 'Draft story not found', details: {} } },
            404,
            corsOrigin,
          );
        }
        return adminJson({ ok: true, data: { story_id: storyId, editorial_hold: 1 } }, 200, corsOrigin);
      }

      // POST /api/v1/admin/story/:id/release — allow auto-publishing to resume
      const releaseMatch = /^\/api\/v1\/admin\/story\/([^/]+)\/release$/.exec(pathname);
      if (request.method === 'POST' && releaseMatch !== null) {
        const storyId = releaseMatch[1]!;
        const updated = await releaseStory(env.DB, storyId);
        if (!updated) {
          return adminJson(
            { ok: false, error: { code: 'not_found', message: 'Story not found', details: {} } },
            404,
            corsOrigin,
          );
        }
        return adminJson({ ok: true, data: { story_id: storyId, editorial_hold: 0 } }, 200, corsOrigin);
      }

      // POST /api/v1/admin/cron/trigger — fire runIngest outside cron schedule
      if (request.method === 'POST' && pathname === '/api/v1/admin/cron/trigger') {
        if (env.CRON_ENABLED !== 'true') {
          return adminJson(
            { ok: false, error: { code: 'cron_disabled', message: 'CRON_ENABLED is not true' } },
            400,
            corsOrigin,
          );
        }
        ctx.waitUntil(runIngest(env));
        return adminJson(
          { ok: true, message: 'Cron run triggered. Check /api/v1/admin/runs in ~15s.' },
          200,
          corsOrigin,
        );
      }
    }

    // GET /api/v1/feed
    if (request.method === 'GET' && pathname === '/api/v1/feed') {
      const result = await getFeed(
        env.DB,
        url.searchParams.get('limit'),
        url.searchParams.get('cursor'),
      );
      if ('type' in result) {
        return err(400, 'invalid_request', result.message, result.details);
      }
      return json({ ok: true, data: result });
    }

    // GET /api/v1/story/:id
    const storyMatch = /^\/api\/v1\/story\/([^/]+)$/.exec(pathname);
    if (request.method === 'GET' && storyMatch !== null) {
      const storyId = storyMatch[1]!;
      const story = await getStory(env.DB, storyId);
      if (story === null) {
        return err(404, 'not_found', 'Story not found', { story_id: storyId });
      }
      return json({ ok: true, data: { story } });
    }

    // 404 fallback
    return err(404, 'not_found', 'Not found', { path: pathname });
  } catch {
    return err(500, 'internal_error', 'An unexpected error occurred');
  }
}
