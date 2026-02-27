import type { ExecutionContext } from '@cloudflare/workers-types';
import type { Env } from './index';

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

export async function route(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);
  const { pathname } = url;

  // GET /api/v1/health
  if (request.method === 'GET' && pathname === '/api/v1/health') {
    return json({
      ok: true,
      service: {
        name: 'news-hub',
        version: '0.1.0',
        env: env.ADMIN_ENABLED === 'true' ? 'dev' : 'prod',
        now_utc: new Date().toISOString(),
      },
      last_run: null,
    });
  }

  // GET /api/v1/feed
  if (request.method === 'GET' && pathname === '/api/v1/feed') {
    return json({
      ok: true,
      data: {
        stories: [],
        next_cursor: null,
      },
    });
  }

  // GET /api/v1/story/:id
  const storyMatch = /^\/api\/v1\/story\/([^/]+)$/.exec(pathname);
  if (request.method === 'GET' && storyMatch !== null) {
    const storyId = storyMatch[1];
    return json(
      {
        ok: false,
        error: {
          code: 'not_found',
          message: 'Story not found',
          details: { story_id: storyId },
        },
      },
      404,
    );
  }

  // 404 fallback
  return json(
    {
      ok: false,
      error: { code: 'not_found', message: 'Not found', details: { path: pathname } },
    },
    404,
  );
}
