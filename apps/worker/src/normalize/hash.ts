/**
 * Compute SHA-256 hex digest of a UTF-8 string.
 * Uses the Web Crypto API available in both Cloudflare Workers and Node.js 20+.
 */
export async function hashHex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
