-- db/migrations/002_editorial_hold.sql
-- Add editorial_hold flag to stories for manual review before auto-publishing.
-- Default 0 (not held): all existing stories continue to publish normally.
-- When editorial_hold = 1: story stays in state='draft', summary pipeline skips it.
-- An admin must explicitly release the hold via POST /api/v1/admin/story/:id/release.

ALTER TABLE stories ADD COLUMN editorial_hold INTEGER NOT NULL DEFAULT 0;

-- Partial index — only held stories (typically very few), avoids full-table scans.
CREATE INDEX IF NOT EXISTS idx_stories_editorial_hold ON stories(editorial_hold) WHERE editorial_hold = 1;
