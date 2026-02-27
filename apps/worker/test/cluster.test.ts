import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clusterNewItems } from '../src/cluster/cluster';
import * as StoriesRepo from '../src/db/stories_repo';
import * as StoryItemsRepo from '../src/db/story_items_repo';

vi.mock('../src/db/stories_repo');
vi.mock('../src/db/story_items_repo');

const DB = null as unknown as D1Database;

function makeItem(
  itemKey: string,
  titleHe: string,
  publishedAt: string | null = null,
) {
  return { itemKey, titleHe, publishedAt };
}

beforeEach(() => {
  vi.resetAllMocks();
  // Safe defaults so tests that don't need specific return values still work.
  vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([]);
  vi.mocked(StoriesRepo.createStory).mockResolvedValue(undefined);
  vi.mocked(StoriesRepo.updateStoryLastUpdate).mockResolvedValue(undefined);
  vi.mocked(StoryItemsRepo.attachItem).mockResolvedValue(true);
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Empty input
// ---------------------------------------------------------------------------
describe('clusterNewItems — empty input', () => {
  it('returns zeros without hitting DB', async () => {
    const counters = await clusterNewItems(DB, []);
    expect(counters).toEqual({ storiesNew: 0, storiesUpdated: 0 });
    expect(StoriesRepo.findRecentStories).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// New story creation
// ---------------------------------------------------------------------------
describe('clusterNewItems — new story', () => {
  it('creates a story when no candidates exist', async () => {
    const counters = await clusterNewItems(DB, [
      makeItem('key1', 'שריפה גדולה בחיפה'),
    ]);
    expect(StoriesRepo.createStory).toHaveBeenCalledOnce();
    expect(StoryItemsRepo.attachItem).toHaveBeenCalledOnce();
    expect(counters.storiesNew).toBe(1);
    expect(counters.storiesUpdated).toBe(0);
  });

  it('uses publishedAt as start_at when provided', async () => {
    const pubDate = '2026-02-27T10:00:00.000Z';
    await clusterNewItems(DB, [
      makeItem('key1', 'שריפה בחיפה', pubDate),
    ]);
    expect(StoriesRepo.createStory).toHaveBeenCalledWith(
      DB,
      expect.any(String), // runId
      pubDate,
    );
  });

  it('uses now as start_at when publishedAt is null', async () => {
    await clusterNewItems(DB, [makeItem('key1', 'שריפה בחיפה', null)]);
    const callArgs = vi.mocked(StoriesRepo.createStory).mock.calls[0];
    // start_at should be a valid ISO string
    expect(() => new Date(callArgs![2] as string)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Matching existing story
// ---------------------------------------------------------------------------
describe('clusterNewItems — attach to existing story', () => {
  it('attaches a similar item to an existing story', async () => {
    vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([
      {
        storyId: 'story-1',
        lastUpdateAt: new Date().toISOString(),
        titleHe: 'ביבי נפגש עם מנהיגים אירופאים',
      },
    ]);

    const counters = await clusterNewItems(DB, [
      makeItem('key2', 'ביבי נפגש עם נשיאים אירופאים'),
    ]);

    expect(StoriesRepo.createStory).not.toHaveBeenCalled();
    expect(StoryItemsRepo.attachItem).toHaveBeenCalledWith(
      DB,
      'story-1',
      'key2',
      expect.any(String),
    );
    expect(StoriesRepo.updateStoryLastUpdate).toHaveBeenCalledWith(
      DB,
      'story-1',
      expect.any(String),
    );
    expect(counters.storiesNew).toBe(0);
    expect(counters.storiesUpdated).toBe(1);
  });

  it('does not update story if attachItem returns false (already attached)', async () => {
    vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([
      {
        storyId: 'story-1',
        lastUpdateAt: new Date().toISOString(),
        titleHe: 'ביבי נפגש עם מנהיגים אירופאים',
      },
    ]);
    vi.mocked(StoryItemsRepo.attachItem).mockResolvedValue(false);

    const counters = await clusterNewItems(DB, [
      makeItem('key2', 'ביבי נפגש עם נשיאים אירופאים'),
    ]);

    expect(StoriesRepo.updateStoryLastUpdate).not.toHaveBeenCalled();
    expect(counters.storiesUpdated).toBe(0);
  });

  it('creates new story for dissimilar item', async () => {
    vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([
      {
        storyId: 'story-1',
        lastUpdateAt: new Date().toISOString(),
        titleHe: 'שריפה בחיפה',
      },
    ]);

    const counters = await clusterNewItems(DB, [
      makeItem('key2', 'רעידת אדמה בתורכיה'),
    ]);

    expect(StoriesRepo.createStory).toHaveBeenCalledOnce();
    expect(counters.storiesNew).toBe(1);
    expect(counters.storiesUpdated).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Multiple items — in-run story matching
// ---------------------------------------------------------------------------
describe('clusterNewItems — multiple items', () => {
  it('second item can match a story created by the first item in the same run', async () => {
    // No existing stories
    vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([]);

    const counters = await clusterNewItems(DB, [
      makeItem('key1', 'ביבי נפגש עם מנהיגים אירופאים'),
      makeItem('key2', 'ביבי נפגש עם נשיאים אירופאים'), // similar to key1
    ]);

    // key1 → new story; key2 → attaches to same story
    expect(counters.storiesNew).toBe(1);
    expect(counters.storiesUpdated).toBe(1);
    expect(StoriesRepo.createStory).toHaveBeenCalledOnce();
  });

  it('two unrelated items produce two stories', async () => {
    vi.mocked(StoriesRepo.findRecentStories).mockResolvedValue([]);

    const counters = await clusterNewItems(DB, [
      makeItem('key1', 'שריפה גדולה בחיפה'),
      makeItem('key2', 'רעידת אדמה בתורכיה'),
    ]);

    expect(counters.storiesNew).toBe(2);
    expect(counters.storiesUpdated).toBe(0);
    expect(StoriesRepo.createStory).toHaveBeenCalledTimes(2);
  });
});
