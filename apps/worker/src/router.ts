import type { ExecutionContext } from '@cloudflare/workers-types';
import type { Env } from './index';
import { getLastRun, getTopFailingSources } from './api/health';
import { getRecentRuns, getRunErrors } from './api/admin';
import { getFeed } from './api/feed';
import { getStory } from './api/story';

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

function err(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
  return json({ ok: false, error: { code, message, details } }, status);
}

export async function route(
  request: Request,
  env: Env,
  _ctx: ExecutionContext,
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

    // Admin routes — gated by ADMIN_ENABLED
    if (pathname.startsWith('/api/v1/admin/')) {
      if (env.ADMIN_ENABLED !== 'true') {
        return err(403, 'forbidden', 'Admin endpoints are disabled');
      }

      // GET /api/v1/admin/runs
      if (request.method === 'GET' && pathname === '/api/v1/admin/runs') {
        const runs = await getRecentRuns(env.DB);
        return json({ ok: true, data: { runs } });
      }

      // GET /api/v1/admin/errors?run_id=X
      if (request.method === 'GET' && pathname === '/api/v1/admin/errors') {
        const runId = url.searchParams.get('run_id');
        if (!runId) return err(400, 'invalid_request', 'run_id query param required');
        const errors = await getRunErrors(env.DB, runId);
        return json({ ok: true, data: { errors } });
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
