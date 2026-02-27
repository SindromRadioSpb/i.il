// Tracking query parameters stripped during normalization.
const TRACKING_PARAMS = new Set([
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
  'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
  'fbclid', 'gclid', 'msclkid', 'twclid', 'igshid',
  'ref', '_ga', 'mc_cid', 'mc_eid',
]);

// IPv4 private ranges + loopback.
const PRIVATE_IP_RE = [
  /^127\./,
  /^10\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^192\.168\./,
  /^0\./,
];

/**
 * SSRF guard: throw if the URL is not safe to fetch from a Worker.
 * Blocks non-http(s) schemes, localhost, and private IP ranges.
 */
export function validateUrlForFetch(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Invalid URL: ${url}`);
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`Disallowed URL scheme: ${parsed.protocol}`);
  }

  const host = parsed.hostname.toLowerCase();

  if (host === 'localhost' || host === '0.0.0.0') {
    throw new Error(`Disallowed URL host: ${host}`);
  }

  // IPv6 loopback
  if (host === '::1' || host === '[::1]') {
    throw new Error(`Disallowed private IP: ${host}`);
  }

  for (const re of PRIVATE_IP_RE) {
    if (re.test(host)) {
      throw new Error(`Disallowed private IP: ${host}`);
    }
  }
}

/**
 * Normalize a URL for stable deduplication:
 * - lowercase scheme + host
 * - strip fragment
 * - strip tracking query params
 * - sort remaining params for stability
 * - strip trailing slash from non-root paths
 */
export function normalizeUrl(rawUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl.trim());
  } catch {
    // Not a valid URL — return lowercased trimmed original as fallback
    return rawUrl.trim().toLowerCase();
  }

  parsed.protocol = parsed.protocol.toLowerCase();
  parsed.hostname = parsed.hostname.toLowerCase();

  // Remove fragment
  parsed.hash = '';

  // Strip tracking params
  for (const key of [...parsed.searchParams.keys()]) {
    if (TRACKING_PARAMS.has(key.toLowerCase())) {
      parsed.searchParams.delete(key);
    }
  }

  // Sort remaining params for stability
  parsed.searchParams.sort();

  // Strip trailing slash from non-root paths
  if (parsed.pathname !== '/' && parsed.pathname.endsWith('/')) {
    parsed.pathname = parsed.pathname.slice(0, -1);
  }

  return parsed.toString();
}
