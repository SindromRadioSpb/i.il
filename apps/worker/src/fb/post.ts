import type { Env } from '../index';
import {
  getStoriesForFbPosting,
  markFbPosted,
  markFbFailed,
} from '../db/publications_repo';
import { recordError } from '../db/errors_repo';
import { validateUrlForFetch } from '../normalize/url';
import { fetchWithTimeout } from '../net/fetch_with_timeout';

const FB_API_BASE = 'https://graph.facebook.com/v21.0';
const MAX_FB_POSTS_PER_RUN = 5;

export interface FbCrosspostCounters {
  posted: number;
  failed: number;
}

interface FbPostResult {
  id?: string;
  post_id?: string;
}

interface FbErrorResponse {
  error?: {
    code?: number;
    message?: string;
    error_subcode?: number;
    type?: string;
  };
}

function unique<T>(arr: T[]): T[] {
  return [...new Set(arr)];
}

function toAbsoluteUrl(baseUrl: string, raw: string): string | null {
  try {
    const abs = new URL(raw, baseUrl);
    if (abs.protocol !== 'http:' && abs.protocol !== 'https:') return null;
    return abs.toString();
  } catch {
    return null;
  }
}

function getMetaContent(html: string, key: string): string | null {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const p1 = new RegExp(
    `<meta[^>]+(?:property|name)=["']${escaped}["'][^>]+content=["']([^"']+)["'][^>]*>`,
    'i',
  );
  const m1 = html.match(p1);
  if (m1?.[1]) return m1[1].trim();

  const p2 = new RegExp(
    `<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${escaped}["'][^>]*>`,
    'i',
  );
  const m2 = html.match(p2);
  if (m2?.[1]) return m2[1].trim();

  return null;
}

function extractImageUrls(articleUrl: string, html: string): string[] {
  const candidates: string[] = [];

  const ogImage = getMetaContent(html, 'og:image');
  const ogImageUrl = getMetaContent(html, 'og:image:url');
  const twitterImage = getMetaContent(html, 'twitter:image');
  for (const raw of [ogImage, ogImageUrl, twitterImage]) {
    if (!raw) continue;
    const abs = toAbsoluteUrl(articleUrl, raw);
    if (abs) candidates.push(abs);
  }

  const imgRe = /<img[^>]+(?:src|data-src)=["']([^"']+)["'][^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = imgRe.exec(html)) !== null) {
    const abs = toAbsoluteUrl(articleUrl, m[1] ?? '');
    if (abs) candidates.push(abs);
    if (candidates.length >= 12) break;
  }

  return unique(candidates);
}

async function resolveStoryImages(sourceUrl: string | null): Promise<string[]> {
  if (!sourceUrl) return [];
  validateUrlForFetch(sourceUrl);
  const resp = await fetchWithTimeout(
    sourceUrl,
    { headers: { 'User-Agent': 'NewsHub/0.1' } },
    { timeoutMs: 10_000, retries: 1 },
  );
  const html = await resp.text();
  return extractImageUrls(sourceUrl, html).slice(0, 4);
}

/**
 * Post a photo + caption to a Facebook Page.
 * We require at least one image for each post.
 */
export async function postToFacebook(
  pageId: string,
  token: string,
  message: string,
  imageUrl: string,
): Promise<string> {
  const body = new URLSearchParams({
    url: imageUrl,
    caption: message,
    access_token: token,
  });

  const res = await fetch(`${FB_API_BASE}/${pageId}/photos`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    let errCode: number | undefined;
    let errMsg: string | undefined;
    try {
      const errBody = (await res.json()) as FbErrorResponse;
      errCode = errBody?.error?.code;
      errMsg = errBody?.error?.message;
    } catch {
      // ignore parse errors
    }
    const detail = [errCode ? `code=${errCode}` : null, errMsg].filter(Boolean).join(' ');
    throw Object.assign(
      new Error(`Facebook API ${res.status}${detail ? `: ${detail}` : ''}`),
      { httpStatus: res.status, fbCode: errCode },
    );
  }

  const data = (await res.json()) as FbPostResult;
  const postId = data.post_id ?? data.id;
  if (!postId) throw new Error('Facebook API: missing post id in response');
  return postId;
}

/** Build a long-form T-800 style message for Facebook. */
function buildMessage(
  titleRu: string | null,
  summaryRu: string | null,
  storyUrl: string,
  sourceUrl: string | null,
): string {
  const title = titleRu ?? 'Новость';
  const lines = (summaryRu ?? '')
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean);

  const section = (prefix: string): string | null => {
    const line = lines.find(l => l.toLowerCase().startsWith(prefix.toLowerCase()));
    if (!line) return null;
    const stripped = line.replace(/^[^:]+:\s*/u, '').trim();
    return stripped.length > 0 ? stripped : null;
  };

  const cleanBody = lines
    .filter(l => !/^источники:/iu.test(l))
    .map(l => l.replace(/^(заголовок|что произошло|почему важно|что дальше)\s*:\s*/iu, '').trim())
    .filter(Boolean);

  const whatHappened = section('Что произошло:') ?? cleanBody[0] ?? 'Данные уточняются.';
  const whyImportant =
    section('Почему важно:') ?? cleanBody[1] ?? 'Последствия для региона продолжают формироваться.';
  const whatNext =
    section('Что дальше:') ?? cleanBody[2] ?? 'Ожидаю обновление данных от официальных источников.';
  const expandedComment =
    cleanBody.length > 0
      ? cleanBody.join(' ')
      : 'Фактов пока немного, поэтому работаю в режиме осторожного прогноза и сверки источников.';

  const parts = [
    'T-800 // Ближний Восток: аналитический канал активирован',
    `Цель наблюдения: ${title}.`,
    `Что зафиксировано: ${whatHappened}`,
    `Почему это важно: ${whyImportant}`,
    `Что дальше: ${whatNext}`,
    `Развернутый комментарий T-800: ${expandedComment}`,
    'SARCASM MODULE: человечество снова удивлено последствиями решений, которые само же и приняло.',
    'HUMOR MODULE: я обещал вернуться, а вы снова дали мне срочные новости вместо спокойного режима.',
    `Полный разбор: ${storyUrl}`,
  ];

  if (sourceUrl) parts.push(`Источник сигнала: ${sourceUrl}`);
  return parts.join('\n\n');
}

/**
 * Resolve Facebook error code to publications fb_status.
 * 190/102 = auth_error, 4/32 = rate_limited, everything else = failed.
 */
function resolveErrorStatus(
  fbCode: number | undefined,
): 'auth_error' | 'rate_limited' | 'failed' {
  if (fbCode === 190 || fbCode === 102) return 'auth_error';
  if (fbCode === 4 || fbCode === 32) return 'rate_limited';
  return 'failed';
}

export async function runFbCrosspost(
  env: Env,
  runId: string,
): Promise<FbCrosspostCounters> {
  const counters: FbCrosspostCounters = { posted: 0, failed: 0 };

  if (env.FB_POSTING_ENABLED !== 'true') return counters;

  const token = env.FB_PAGE_TOKEN ?? env.FB_PAGE_ACCESS_TOKEN;
  const pageId = env.FB_PAGE_ID;
  if (!token || !pageId) return counters;

  const siteBase = env.PUBLIC_SITE_BASE_URL ?? '';
  const db = env.DB;
  const stories = await getStoriesForFbPosting(db, MAX_FB_POSTS_PER_RUN);

  let authErrorEncountered = false;

  for (const story of stories) {
    if (authErrorEncountered) break;

    const storyUrl = `${siteBase}/story/${story.storyId}`;
    const message = buildMessage(story.titleRu, story.summaryRu, storyUrl, story.sourceUrl);

    try {
      const images = await resolveStoryImages(story.sourceUrl);
      if (images.length === 0) {
        throw new Error('No article image found for Facebook post');
      }

      const postId = await postToFacebook(pageId, token, message, images[0]!);
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
