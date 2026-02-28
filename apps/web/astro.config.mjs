import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  output: 'server',
  adapter: cloudflare(),
  site: process.env.PUBLIC_SITE_BASE_URL ?? 'https://news-hub.pages.dev',
  integrations: [sitemap()],
});
