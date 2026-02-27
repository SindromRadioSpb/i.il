import { z } from 'zod';

export const ThrottleSchema = z.object({
  min_interval_sec: z.number().int().positive(),
  max_items_per_run: z.number().int().positive(),
});

export const SourceSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  type: z.enum(['rss', 'sitemap', 'html']),
  url: z.string().url(),
  lang: z.string().default('he'),
  enabled: z.boolean(),
  throttle: ThrottleSchema.optional(),
  category_hints: z.array(z.string()).default([]),
  parser: z.record(z.string(), z.unknown()).optional(),
});

export type Source = z.infer<typeof SourceSchema>;
export type SourceType = Source['type'];
