-- db/schema.sql
-- Snapshot of schema after migrations up to 001_init.sql
-- Generated manually for initial scaffold. Keep in sync with migrations.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  item_key TEXT NOT NULL,
  title_he TEXT NOT NULL,
  published_at TEXT,
  updated_at TEXT,
  date_confidence TEXT NOT NULL DEFAULT 'low',
  snippet_he TEXT,
  title_hash TEXT,
  content_hash TEXT,
  ingested_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_items_item_key_unique ON items(item_key);
CREATE INDEX IF NOT EXISTS idx_items_source_published ON items(source_id, published_at);
CREATE INDEX IF NOT EXISTS idx_items_ingested_at ON items(ingested_at);

CREATE TABLE IF NOT EXISTS stories (
  story_id TEXT PRIMARY KEY,
  story_key TEXT,
  start_at TEXT NOT NULL,
  last_update_at TEXT NOT NULL,
  title_ru TEXT,
  summary_ru TEXT,
  summary_hash TEXT,
  summary_version INTEGER NOT NULL DEFAULT 0,
  category TEXT NOT NULL DEFAULT 'other',
  risk_level TEXT NOT NULL DEFAULT 'low',
  state TEXT NOT NULL DEFAULT 'draft'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_stories_story_key_unique ON stories(story_key) WHERE story_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stories_last_update ON stories(last_update_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_state_last_update ON stories(state, last_update_at DESC);

CREATE TABLE IF NOT EXISTS story_items (
  story_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  added_at TEXT NOT NULL,
  rank INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (story_id, item_id),
  FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_story_items_story_rank ON story_items(story_id, rank);
CREATE INDEX IF NOT EXISTS idx_story_items_item ON story_items(item_id);

CREATE TABLE IF NOT EXISTS publications (
  story_id TEXT PRIMARY KEY,
  web_status TEXT NOT NULL DEFAULT 'pending',
  web_published_at TEXT,
  fb_status TEXT NOT NULL DEFAULT 'disabled',
  fb_post_id TEXT,
  fb_posted_at TEXT,
  fb_error_last TEXT,
  fb_attempts INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_publications_web_status ON publications(web_status);
CREATE INDEX IF NOT EXISTS idx_publications_fb_status ON publications(fb_status);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  sources_ok INTEGER NOT NULL DEFAULT 0,
  sources_failed INTEGER NOT NULL DEFAULT 0,
  items_found INTEGER NOT NULL DEFAULT 0,
  items_new INTEGER NOT NULL DEFAULT 0,
  stories_new INTEGER NOT NULL DEFAULT 0,
  stories_updated INTEGER NOT NULL DEFAULT 0,
  published_web INTEGER NOT NULL DEFAULT 0,
  published_fb INTEGER NOT NULL DEFAULT 0,
  errors_total INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);

CREATE TABLE IF NOT EXISTS run_lock (
  lock_name TEXT PRIMARY KEY,
  lease_owner TEXT NOT NULL,
  lease_until TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS error_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  source_id TEXT,
  story_id TEXT,
  code TEXT,
  message TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_error_events_run_id ON error_events(run_id);
CREATE INDEX IF NOT EXISTS idx_error_events_source_created ON error_events(source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_events_phase_created ON error_events(phase, created_at DESC);
