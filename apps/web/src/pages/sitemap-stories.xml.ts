import type { APIRoute } from 'astro';
import { fetchFeed } from '../lib/api';

export const GET: APIRoute = async () => {
  const siteBase = import.meta.env.PUBLIC_SITE_BASE_URL ?? '';
  const urls: string[] = [];

  let cursor: string | undefined;
  // Fetch up to 200 published stories for the sitemap
  for (let page = 0; page < 4; page++) {
    try {
      const resp = await fetchFeed(50, cursor);
      if (!resp.ok) break;
      for (const s of resp.data.stories) {
        urls.push(`${siteBase}/story/${s.story_id}`);
      }
      if (!resp.data.next_cursor) break;
      cursor = resp.data.next_cursor;
    } catch {
      break;
    }
  }

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>${siteBase}/</loc></url>
${urls.map((url) => `  <url><loc>${url}</loc></url>`).join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
