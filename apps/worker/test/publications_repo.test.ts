import { describe, expect, it } from 'vitest';
import {
  getStoriesForFbPosting,
  markFbPosted,
  markFbFailed,
} from '../src/db/publications_repo';

function makeDb(rows: object[] = []) {
  let lastSql = '';
  const stmt = {
    bind: function (..._args: unknown[]) {
      return this;
    },
    all: <T>() => Promise.resolve({ results: rows as T[], success: true, meta: {} }),
    run: () => Promise.resolve({ success: true, meta: { changes: 1 } }),
  };
  const db = {
    prepare: (sql: string) => {
      lastSql = sql;
      return stmt;
    },
    _sql: () => lastSql,
  };
  return db as unknown as D1Database & { _sql: () => string };
}

describe('getStoriesForFbPosting query guards', () => {
  it('SQL includes fb_attempts < 5 cap', async () => {
    const db = makeDb();
    await getStoriesForFbPosting(db, 5);
    expect(db._sql()).toContain('fb_attempts < 5');
  });

  it('SQL includes fb_post_id IS NULL idempotency guard', async () => {
    const db = makeDb();
    await getStoriesForFbPosting(db, 5);
    expect(db._sql()).toContain('fb_post_id IS NULL');
  });

  it('SQL retries failed status but not auth_error/rate_limited', async () => {
    const db = makeDb();
    await getStoriesForFbPosting(db, 5);
    const sql = db._sql();
    expect(sql).toContain("'disabled'");
    expect(sql).toContain("'failed'");
    expect(sql).not.toContain("'auth_error'");
    expect(sql).not.toContain("'rate_limited'");
  });

  it('maps DB rows including source_url', async () => {
    const db = makeDb([
      {
        story_id: 'abc',
        title_ru: 'Заголовок',
        summary_ru: 'Текст',
        source_url: 'https://www.ynet.co.il/news/article/abc',
      },
    ]);
    const result = await getStoriesForFbPosting(db, 5);
    expect(result).toEqual([
      {
        storyId: 'abc',
        titleRu: 'Заголовок',
        summaryRu: 'Текст',
        sourceUrl: 'https://www.ynet.co.il/news/article/abc',
      },
    ]);
  });
});

describe('markFbPosted', () => {
  it('runs without throwing and updates posted fields', async () => {
    const db = makeDb();
    await expect(markFbPosted(db, 'story-1', 'post-123')).resolves.toBeUndefined();
    expect(db._sql()).toContain("fb_status = 'posted'");
    expect(db._sql()).toContain('fb_post_id');
  });
});

describe('markFbFailed', () => {
  it('increments attempts and stores last error', async () => {
    const db = makeDb();
    await expect(markFbFailed(db, 'story-1', 'failed', 'some error')).resolves.toBeUndefined();
    expect(db._sql()).toContain('fb_attempts = fb_attempts + 1');
    expect(db._sql()).toContain('fb_error_last');
  });

  it('accepts all valid failure statuses', async () => {
    const db = makeDb();
    for (const status of ['failed', 'auth_error', 'rate_limited'] as const) {
      await expect(markFbFailed(db, 'story-1', status, 'err')).resolves.toBeUndefined();
    }
  });
});
