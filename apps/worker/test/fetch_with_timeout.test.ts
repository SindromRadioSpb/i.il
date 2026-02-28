import { describe, expect, it, vi, afterEach } from 'vitest';
import { fetchWithTimeout } from '../src/net/fetch_with_timeout';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchWithTimeout', () => {
  it('returns response on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    );
    const res = await fetchWithTimeout('https://example.com/feed.xml');
    expect(res.ok).toBe(true);
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it('retries once on 429 and succeeds on second attempt', async () => {
    let calls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        calls++;
        if (calls === 1) return { ok: false, status: 429, headers: new Headers() };
        return { ok: true, status: 200 };
      }),
    );
    const res = await fetchWithTimeout('https://example.com', undefined, {
      retries: 1,
      retryDelayMs: 0,
    });
    expect(res.ok).toBe(true);
    expect(calls).toBe(2);
  });

  it('retries once on 503 and succeeds on second attempt', async () => {
    let calls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        calls++;
        if (calls === 1) return { ok: false, status: 503, headers: new Headers() };
        return { ok: true, status: 200 };
      }),
    );
    const res = await fetchWithTimeout('https://example.com', undefined, {
      retries: 1,
      retryDelayMs: 0,
    });
    expect(res.ok).toBe(true);
    expect(calls).toBe(2);
  });

  it('throws after retries exhausted on 429', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 429, headers: new Headers() }),
    );
    await expect(
      fetchWithTimeout('https://example.com', undefined, { retries: 1, retryDelayMs: 0 }),
    ).rejects.toThrow('HTTP 429');
    // 1 initial + 1 retry = 2 calls
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
  });

  it('throws immediately on 400 (non-transient, no retry)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 400, headers: new Headers() }),
    );
    await expect(
      fetchWithTimeout('https://example.com', undefined, { retries: 1 }),
    ).rejects.toThrow('HTTP 400');
    // Only 1 call — no retry for 400
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it('throws immediately on 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404, headers: new Headers() }),
    );
    await expect(
      fetchWithTimeout('https://example.com', undefined, { retries: 1 }),
    ).rejects.toThrow('HTTP 404');
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it('uses Retry-After header delay when present', async () => {
    const delays: number[] = [];
    vi.stubGlobal('setTimeout', (fn: () => void, ms: number) => {
      delays.push(ms);
      fn(); // execute immediately in tests
      return 0;
    });

    let calls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        calls++;
        if (calls === 1) {
          const headers = new Headers({ 'retry-after': '2' }); // 2 seconds
          return { ok: false, status: 429, headers };
        }
        return { ok: true, status: 200 };
      }),
    );

    await fetchWithTimeout('https://example.com', undefined, {
      retries: 1,
      retryDelayMs: 1_000,
    });

    // Should use Retry-After (2000ms) instead of default retryDelayMs (1000ms)
    expect(delays[0]).toBe(2_000);
  });

  it('passes AbortSignal to underlying fetch', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200 }),
    );
    await fetchWithTimeout('https://example.com', {}, { timeoutMs: 5_000 });
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});
