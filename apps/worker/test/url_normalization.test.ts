import { describe, expect, it } from 'vitest';
import { normalizeUrl, validateUrlForFetch } from '../src/normalize/url';

// ---------------------------------------------------------------------------
// normalizeUrl
// ---------------------------------------------------------------------------
describe('normalizeUrl', () => {
  it('strips utm_* tracking params', () => {
    const result = normalizeUrl(
      'https://example.com/path?utm_source=rss&utm_medium=feed&keep=1',
    );
    expect(result).not.toContain('utm_source');
    expect(result).not.toContain('utm_medium');
    expect(result).toContain('keep=1');
  });

  it('strips fbclid and gclid', () => {
    const result = normalizeUrl('https://example.com/p?fbclid=abc&gclid=xyz&id=5');
    expect(result).not.toContain('fbclid');
    expect(result).not.toContain('gclid');
    expect(result).toContain('id=5');
  });

  it('sorts remaining query params for stability', () => {
    const a = normalizeUrl('https://example.com/?z=1&a=2');
    const b = normalizeUrl('https://example.com/?a=2&z=1');
    expect(a).toBe(b);
  });

  it('lowercases scheme and hostname', () => {
    const result = normalizeUrl('HTTPS://WWW.Example.COM/path');
    expect(result.startsWith('https://www.example.com/')).toBe(true);
  });

  it('strips fragment (#)', () => {
    const result = normalizeUrl('https://example.com/path#section');
    expect(result).not.toContain('#');
  });

  it('strips trailing slash from non-root paths', () => {
    expect(normalizeUrl('https://example.com/news/')).toBe(
      'https://example.com/news',
    );
  });

  it('preserves root slash', () => {
    expect(normalizeUrl('https://example.com/')).toBe('https://example.com/');
  });

  it('returns lowercased original for invalid URLs', () => {
    const result = normalizeUrl('not-a-url');
    expect(result).toBe('not-a-url');
  });
});

// ---------------------------------------------------------------------------
// validateUrlForFetch (SSRF guard)
// ---------------------------------------------------------------------------
describe('validateUrlForFetch', () => {
  it('allows plain https URL', () => {
    expect(() => validateUrlForFetch('https://example.com/rss')).not.toThrow();
  });

  it('allows plain http URL', () => {
    expect(() => validateUrlForFetch('http://example.com/rss')).not.toThrow();
  });

  it('throws for file:// scheme', () => {
    expect(() => validateUrlForFetch('file:///etc/passwd')).toThrow(
      'Disallowed URL scheme',
    );
  });

  it('throws for ftp:// scheme', () => {
    expect(() => validateUrlForFetch('ftp://example.com/')).toThrow(
      'Disallowed URL scheme',
    );
  });

  it('throws for localhost', () => {
    expect(() => validateUrlForFetch('http://localhost/admin')).toThrow(
      'Disallowed URL host',
    );
  });

  it('throws for 0.0.0.0', () => {
    expect(() => validateUrlForFetch('http://0.0.0.0/')).toThrow(
      'Disallowed URL host',
    );
  });

  it('throws for IPv6 loopback ::1', () => {
    expect(() => validateUrlForFetch('http://[::1]/')).toThrow(
      'Disallowed private IP',
    );
  });

  it('throws for 127.x (loopback)', () => {
    expect(() => validateUrlForFetch('http://127.0.0.1/')).toThrow(
      'Disallowed private IP',
    );
  });

  it('throws for 10.x (private)', () => {
    expect(() => validateUrlForFetch('http://10.0.0.1/')).toThrow(
      'Disallowed private IP',
    );
  });

  it('throws for 192.168.x (private)', () => {
    expect(() => validateUrlForFetch('http://192.168.1.1/')).toThrow(
      'Disallowed private IP',
    );
  });

  it('throws for 172.16.x (private)', () => {
    expect(() => validateUrlForFetch('http://172.16.0.1/')).toThrow(
      'Disallowed private IP',
    );
  });

  it('allows 172.15.x (public, just outside private range)', () => {
    expect(() => validateUrlForFetch('http://172.15.0.1/')).not.toThrow();
  });

  it('throws for invalid URL string', () => {
    expect(() => validateUrlForFetch('not a url')).toThrow('Invalid URL');
  });
});
