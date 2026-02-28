import { describe, expect, it } from 'vitest';
import {
  getStoriesForFbPosting,
  markFbPosted,
  markFbFailed,
} from '../src/db/publications_repo';

// ---------------------------------------------------------------------------
// DB stub helpers
// ---------------------------------------------------------------------------

/** Build a D1 stub that captures the SQL passed to prepare() and returns rows. */
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

// ---------------------------------------------------------------------------
// getStoriesForFbPosting
// ---------------------------------------------------------------------------

describe('getStoriesForFbPosting — query guards', () => {
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

  it('SQL retries failed status but not auth_error or rate_limited', async () => {
    const db = makeDb();
    await getStoriesForFbPosting(db, 5);
    const sql = db._sql();
    expect(sql).toContain("'disabled'");
    expect(sql).toContain("'failed'");
    expect(sql).not.toContain("'auth_error'");
    expect(sql).not.toContain("'rate_limited'");
  });

  it('returns empty array when DB returns no rows', async () => {
    const db = makeDb([]);
    const result = await getStoriesForFbPosting(db, 5);
    expect(result).toEqual([]);
  });

  it('maps DB row fields to FbStoryRow correctly', async () => {
    const db = makeDb([
      { story_id: 'abc', title_ru: 'Заголовок', summary_ru: 'Текст' },
    ]);
    const result = await getStoriesForFbPosting(db, 5);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ storyId: 'abc', titleRu: 'Заголовок', summaryRu: 'Текст' });
  });

  it('maps null title_ru and summary_ru without error', async () => {
    const db = makeDb([{ story_id: 'xyz', title_ru: null, summary_ru: null }]);
    const [row] = await getStoriesForFbPosting(db, 5);
    expect(row?.titleRu).toBeNull();
    expect(row?.summaryRu).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// markFbPosted
// ---------------------------------------------------------------------------

describe('markFbPosted', () => {
  it('runs without throwing', async () => {
    const db = makeDb();
    await expect(markFbPosted(db, 'story-1', 'post-123')).resolves.toBeUndefined();
  });

  it('SQL sets fb_status to posted', async () => {
    const db = makeDb();
    await markFbPosted(db, 'story-1', 'post-123');
    expect(db._sql()).toContain("fb_status = 'posted'");
  });

  it('SQL sets fb_post_id', async () => {
    const db = makeDb();
    await markFbPosted(db, 'story-1', 'post-123');
    expect(db._sql()).toContain('fb_post_id');
  });
});

// ---------------------------------------------------------------------------
// markFbFailed
// ---------------------------------------------------------------------------

describe('markFbFailed', () => {
  it('runs without throwing for failed status', async () => {
    const db = makeDb();
    await expect(markFbFailed(db, 'story-1', 'failed', 'some error')).resolves.toBeUndefined();
  });

  it('SQL increments fb_attempts', async () => {
    const db = makeDb();
    await markFbFailed(db, 'story-1', 'auth_error', 'bad token');
    expect(db._sql()).toContain('fb_attempts = fb_attempts + 1');
  });

  it('SQL sets fb_error_last', async () => {
    const db = makeDb();
    await markFbFailed(db, 'story-1', 'rate_limited', 'rate limit hit');
    expect(db._sql()).toContain('fb_error_last');
  });

  it('accepts all valid failure statuses', async () => {
    const db = makeDb();
    for (const status of ['failed', 'auth_error', 'rate_limited'] as const) {
      await expect(markFbFailed(db, 'story-1', status, 'err')).resolves.toBeUndefined();
    }
  });
});
