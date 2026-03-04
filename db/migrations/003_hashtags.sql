-- db/migrations/003_hashtags.sql
-- Add hashtags column to stories table.
-- Populated by the local engine summariser and synced via POST /api/v1/sync/stories.

ALTER TABLE stories ADD COLUMN hashtags TEXT;
