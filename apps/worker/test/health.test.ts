import { describe, expect, it } from 'vitest';
import { route } from '../src/router';

describe('health endpoint', () => {
  it('returns ok=true', async () => {
    const req = new Request('http://local/api/v1/health', { method: 'GET' });
    const res = await route(req, {
      // @ts-expect-error D1Database not needed for this test
      DB: undefined,
      CRON_ENABLED: 'false',
      FB_POSTING_ENABLED: 'false',
      ADMIN_ENABLED: 'true',
      CRON_INTERVAL_MIN: '10',
      MAX_NEW_ITEMS_PER_RUN: '25',
      SUMMARY_TARGET_MIN: '400',
      SUMMARY_TARGET_MAX: '700',
    }, {} as any);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
  });
});
