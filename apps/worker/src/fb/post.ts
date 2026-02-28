import type { Env } from '../index';
import {
  getStoriesForFbPosting,
  markFbPosted,
  markFbFailed,
} from '../db/publications_repo';
import { recordError } from '../db/errors_repo';

const FB_API_BASE = 'https://graph.facebook.com/v21.0';
const MAX_FB_POSTS_PER_RUN = 5;

export interface FbCrosspostCounters {
  posted: number;
  failed: number;
}

interface FbPostResult {
  id: string;
}

interface FbErrorResponse {
  error?: {
    code?: number;
    message?: string;
  };
}

/**
 * Post a message + link to a Facebook Page feed via Graph API.
 * Throws on non-2xx or missing post ID.
 */
export async function postToFacebook(
  pageId: string,
  token: string,
  message: string,
  link: string,
): Promise<string> {
  const res = await fetch(`${FB_API_BASE}/${pageId}/feed`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message, link, access_token: token }),
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    let errCode: number | undefined;
    try {
      const errBody = (await res.json()) as FbErrorResponse;
      errCode = errBody?.error?.code;
    } catch {
      // ignore parse errors
    }
    throw Object.assign(new Error(`Facebook API ${res.status}`), {
      httpStatus: res.status,
      fbCode: errCode,
    });
  }

  const data = (await res.json()) as FbPostResult;
  if (!data.id) throw new Error('Facebook API: missing post id in response');
  return data.id;
}

/** Build the FB post message from story data. */
function buildMessage(
  titleRu: string | null,
  summaryRu: string | null,
  storyUrl: string,
): string {
  const title = titleRu ?? 'Новость';
  const excerptLines = summaryRu
    ? summaryRu.split('\n').filter(l => l.trim()).slice(0, 2).join('\n')
    : '';
  const parts = [`📌 ${title}`];
  if (excerptLines) parts.push(excerptLines);
  parts.push(`Читать полностью → ${storyUrl}`);
  return parts.join('\n\n');
}

/**
 * Resolve Facebook error code to a publications fb_status value.
 * 190 = invalid token, 102 = session key invalid → auth_error (stop posting this run).
 * 4 = app-level rate limit, 32 = page-level rate limit → rate_limited.
 * Anything else → failed.
 */
function resolveErrorStatus(
  fbCode: number | undefined,
): 'auth_error' | 'rate_limited' | 'failed' {
  if (fbCode === 190 || fbCode === 102) return 'auth_error';
  if (fbCode === 4 || fbCode === 32) return 'rate_limited';
  return 'failed';
}

/**
 * Main Facebook crossposting orchestrator.
 * Called from runIngest() when FB_POSTING_ENABLED === 'true'.
 */
export async function runFbCrosspost(
  env: Env,
  runId: string,
): Promise<FbCrosspostCounters> {
  const counters: FbCrosspostCounters = { posted: 0, failed: 0 };

  if (env.FB_POSTING_ENABLED !== 'true') return counters;

  const token = env.FB_PAGE_ACCESS_TOKEN;
  const pageId = env.FB_PAGE_ID;
  if (!token || !pageId) return counters;

  const siteBase = env.PUBLIC_SITE_BASE_URL ?? '';
  const db = env.DB;

  const stories = await getStoriesForFbPosting(db, MAX_FB_POSTS_PER_RUN);

  let authErrorEncountered = false;

  for (const story of stories) {
    if (authErrorEncountered) break;

    const storyUrl = `${siteBase}/story/${story.storyId}`;
    const message = buildMessage(story.titleRu, story.summaryRu, storyUrl);

    try {
      const postId = await postToFacebook(pageId, token, message, storyUrl);
      await markFbPosted(db, story.storyId, postId);
      counters.posted++;
    } catch (err: unknown) {
      counters.failed++;
      const fbCode =
        err instanceof Error && 'fbCode' in err
          ? (err as { fbCode?: number }).fbCode
          : undefined;
      const status = resolveErrorStatus(fbCode);
      if (status === 'auth_error') authErrorEncountered = true;

      await markFbFailed(db, story.storyId, status, err instanceof Error ? err.message : String(err));
      await recordError(db, runId, 'fb_crosspost', null, story.storyId, err);
    }
  }

  return counters;
}
