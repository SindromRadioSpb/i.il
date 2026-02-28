import { describe, expect, it, vi, afterEach } from 'vitest';
import type { FeedResponse, StoryResponse } from '../src/lib/api';

// We test the API client module shapes in isolation (no real network calls).
// The actual fetching is integration-tested via the deployed worker.

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('API client — fetchFeed', () => {
  it('calls /api/v1/feed with limit param', async () => {
    const mockFeed: FeedResponse = {
      ok: true,
      data: { stories: [], next_cursor: null },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockFeed,
    }));
    const { fetchFeed } = await import('../src/lib/api');
    await fetchFeed(10);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain('/api/v1/feed');
    expect(url).toContain('limit=10');
  });

  it('appends cursor when provided', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, data: { stories: [], next_cursor: null } }),
    }));
    const { fetchFeed } = await import('../src/lib/api');
    await fetchFeed(20, 'abc123');
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain('cursor=abc123');
  });

  it('throws on non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    const { fetchFeed } = await import('../src/lib/api');
    await expect(fetchFeed()).rejects.toThrow('Feed API 503');
  });
});

describe('API client — fetchStory', () => {
  it('calls /api/v1/story/:id', async () => {
    const mockStory: StoryResponse = {
      ok: true,
      data: {
        story: {
          story_id: 'story-1',
          canonical_url: '/story/story-1',
          title_ru: 'Тест',
          summary_ru: 'Заголовок: Тест\nЧто произошло: ...',
          category: 'politics',
          risk_level: 'low',
          start_at: '2026-01-01T00:00:00Z',
          last_update_at: '2026-01-01T00:00:00Z',
          sources: [],
          timeline: [],
        },
      },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockStory,
    }));
    const { fetchStory } = await import('../src/lib/api');
    const result = await fetchStory('story-1');
    expect(result.ok).toBe(true);
    expect(result.data.story.story_id).toBe('story-1');
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain('/api/v1/story/story-1');
  });

  it('throws on non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const { fetchStory } = await import('../src/lib/api');
    await expect(fetchStory('missing')).rejects.toThrow('Story API 404');
  });
});
