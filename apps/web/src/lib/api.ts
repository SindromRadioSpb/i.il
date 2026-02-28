/**
 * API client for the News Hub Worker API.
 * Provides typed wrappers around /api/v1/feed and /api/v1/story/:id.
 */

export interface FeedStory {
  story_id: string;
  canonical_url: string;
  title_ru: string | null;
  summary_excerpt_ru: string | null;
  category: string;
  risk_level: string;
  source_count: number;
  start_at: string;
  last_update_at: string;
}

export interface FeedData {
  stories: FeedStory[];
  next_cursor: string | null;
}

export interface FeedResponse {
  ok: boolean;
  data: FeedData;
}

export interface StorySource {
  source_id: string;
  name: string;
  url: string;
}

export interface TimelineItem {
  item_id: string;
  source_id: string;
  title_he: string;
  url: string;
  published_at: string | null;
}

export interface StoryDetail {
  story_id: string;
  canonical_url: string;
  title_ru: string | null;
  summary_ru: string | null;
  category: string;
  risk_level: string;
  start_at: string;
  last_update_at: string;
  sources: StorySource[];
  timeline: TimelineItem[];
}

export interface StoryResponse {
  ok: boolean;
  data: { story: StoryDetail };
}

function apiBase(): string {
  return import.meta.env.PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8787';
}

export async function fetchFeed(limit = 20, cursor?: string): Promise<FeedResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  const res = await fetch(`${apiBase()}/api/v1/feed?${params.toString()}`);
  if (!res.ok) throw new Error(`Feed API ${res.status}`);
  return res.json() as Promise<FeedResponse>;
}

export async function fetchStory(id: string): Promise<StoryResponse> {
  const res = await fetch(`${apiBase()}/api/v1/story/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`Story API ${res.status}`);
  return res.json() as Promise<StoryResponse>;
}
