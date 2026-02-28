/**
 * fetchWithTimeout — fetch wrapper with timeout and single retry on transient errors.
 *
 * Retries on 429 (Too Many Requests) and 503 (Service Unavailable).
 * Parses `Retry-After` header if present (capped at 5s to fit within cron budget).
 * All other non-2xx responses are NOT retried (fail fast).
 */

const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_RETRIES = 1;
const DEFAULT_RETRY_DELAY_MS = 1_000;
const MAX_RETRY_AFTER_MS = 5_000;

const RETRYABLE_STATUSES = new Set([429, 503]);

export interface FetchTimeoutOptions {
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
}

function parseRetryAfterMs(headers: Headers | undefined): number | undefined {
  if (!headers) return undefined;
  const value = headers.get('retry-after');
  if (!value) return undefined;
  const seconds = parseFloat(value);
  if (!isNaN(seconds)) return Math.min(seconds * 1000, MAX_RETRY_AFTER_MS);
  // RFC 7231 HTTP-date format — not worth parsing fully; use default delay
  return undefined;
}

async function sleep(ms: number): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, ms));
}

export async function fetchWithTimeout(
  url: string | Request,
  init?: RequestInit,
  opts: FetchTimeoutOptions = {},
): Promise<Response> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxRetries = opts.retries ?? DEFAULT_RETRIES;
  const baseDelayMs = opts.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;

  let attempt = 0;

  while (true) {
    const signal = AbortSignal.timeout(timeoutMs);

    const res = await fetch(url, { ...init, signal });

    if (res.ok) return res;

    if (RETRYABLE_STATUSES.has(res.status) && attempt < maxRetries) {
      attempt++;
      const retryMs = parseRetryAfterMs(res.headers) ?? baseDelayMs * attempt;
      await sleep(retryMs);
      continue;
    }

    return res; // caller checks res.ok and handles the error
  }
}
