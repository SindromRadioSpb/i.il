"""db/schema.py — All SQLite DDL for the local engine.

Tables are split into two groups:
  1. D1-COMPATIBLE: exact replicas of Cloudflare D1 tables (001_init.sql + 002_editorial_hold.sql).
     Column names, types, and constraints MUST remain identical — item_key values must match
     across both stores for the CF sync push to work correctly.
  2. LOCAL-ONLY: additional tables used only by the local Python engine.

apply_migrations() in migrate.py executes all statements in ALL_DDL in order.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# D1-COMPATIBLE TABLES
# ─────────────────────────────────────────────────────────────────────────────

DDL_ITEMS = """
CREATE TABLE IF NOT EXISTS items (
  item_id        TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL,
  source_url     TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  item_key       TEXT NOT NULL,
  title_he       TEXT NOT NULL,
  published_at   TEXT,
  updated_at     TEXT,
  date_confidence TEXT NOT NULL DEFAULT 'low',
  snippet_he     TEXT,
  title_hash     TEXT,
  content_hash   TEXT,
  ingested_at    TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'new',
  enclosure_url  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_item_key_unique
  ON items(item_key);
CREATE INDEX IF NOT EXISTS idx_items_source_published
  ON items(source_id, published_at);
CREATE INDEX IF NOT EXISTS idx_items_ingested_at
  ON items(ingested_at);
"""

DDL_STORIES = """
CREATE TABLE IF NOT EXISTS stories (
  story_id        TEXT PRIMARY KEY,
  story_key       TEXT,
  start_at        TEXT NOT NULL,
  last_update_at  TEXT NOT NULL,
  title_ru        TEXT,
  summary_ru      TEXT,
  summary_hash    TEXT,
  summary_version INTEGER NOT NULL DEFAULT 0,
  category        TEXT NOT NULL DEFAULT 'other',
  risk_level      TEXT NOT NULL DEFAULT 'low',
  state           TEXT NOT NULL DEFAULT 'draft',
  editorial_hold  INTEGER NOT NULL DEFAULT 0,
  hashtags        TEXT,
  cf_synced_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_stories_story_key_unique
  ON stories(story_key) WHERE story_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stories_last_update
  ON stories(last_update_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_state_last_update
  ON stories(state, last_update_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_editorial_hold
  ON stories(editorial_hold) WHERE editorial_hold = 1;
"""

DDL_STORY_ITEMS = """
CREATE TABLE IF NOT EXISTS story_items (
  story_id TEXT NOT NULL,
  item_id  TEXT NOT NULL,
  added_at TEXT NOT NULL,
  rank     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (story_id, item_id),
  FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id)  REFERENCES items(item_id)   ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_story_items_story_rank
  ON story_items(story_id, rank);
CREATE INDEX IF NOT EXISTS idx_story_items_item
  ON story_items(item_id);
"""

DDL_PUBLICATIONS = """
CREATE TABLE IF NOT EXISTS publications (
  story_id       TEXT PRIMARY KEY,
  web_status     TEXT NOT NULL DEFAULT 'pending',
  web_published_at TEXT,
  fb_status      TEXT NOT NULL DEFAULT 'disabled',
  fb_post_id     TEXT,
  fb_posted_at   TEXT,
  fb_error_last  TEXT,
  fb_attempts    INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_publications_web_status
  ON publications(web_status);
CREATE INDEX IF NOT EXISTS idx_publications_fb_status
  ON publications(fb_status);
"""

DDL_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
  run_id         TEXT PRIMARY KEY,
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  status         TEXT NOT NULL DEFAULT 'in_progress',
  sources_ok     INTEGER NOT NULL DEFAULT 0,
  sources_failed INTEGER NOT NULL DEFAULT 0,
  items_found    INTEGER NOT NULL DEFAULT 0,
  items_new      INTEGER NOT NULL DEFAULT 0,
  stories_new    INTEGER NOT NULL DEFAULT 0,
  stories_updated INTEGER NOT NULL DEFAULT 0,
  published_web  INTEGER NOT NULL DEFAULT 0,
  published_fb   INTEGER NOT NULL DEFAULT 0,
  errors_total   INTEGER NOT NULL DEFAULT 0,
  duration_ms    INTEGER NOT NULL DEFAULT 0,
  error_summary  TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at
  ON runs(started_at DESC);
"""

DDL_RUN_LOCK = """
CREATE TABLE IF NOT EXISTS run_lock (
  lock_name   TEXT PRIMARY KEY,
  lease_owner TEXT NOT NULL,
  lease_until TEXT NOT NULL
);
"""

DDL_ERROR_EVENTS = """
CREATE TABLE IF NOT EXISTS error_events (
  event_id   TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL,
  phase      TEXT NOT NULL,
  source_id  TEXT,
  story_id   TEXT,
  code       TEXT,
  message    TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_error_events_run_id
  ON error_events(run_id);
CREATE INDEX IF NOT EXISTS idx_error_events_source_created
  ON error_events(source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_events_phase_created
  ON error_events(phase, created_at DESC);
"""

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL-ONLY TABLES
# ─────────────────────────────────────────────────────────────────────────────

DDL_SOURCE_STATE = """
CREATE TABLE IF NOT EXISTS source_state (
  source_id            TEXT PRIMARY KEY,
  last_fetch_at        TEXT,
  last_success_at      TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  backoff_until        TEXT,
  total_fetches        INTEGER NOT NULL DEFAULT 0,
  total_items_found    INTEGER NOT NULL DEFAULT 0,
  updated_at           TEXT NOT NULL
);
"""

DDL_IMAGES_CACHE = """
CREATE TABLE IF NOT EXISTS images_cache (
  image_id     TEXT PRIMARY KEY,
  item_id      TEXT,
  story_id     TEXT,
  original_url TEXT NOT NULL,
  local_path   TEXT,
  etag         TEXT,
  content_hash TEXT,
  width        INTEGER,
  height       INTEGER,
  size_bytes   INTEGER,
  mime_type    TEXT,
  cached_at    TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_images_item
  ON images_cache(item_id);
CREATE INDEX IF NOT EXISTS idx_images_story
  ON images_cache(story_id);
CREATE INDEX IF NOT EXISTS idx_images_status
  ON images_cache(status);
"""

DDL_PUBLISH_QUEUE = """
CREATE TABLE IF NOT EXISTS publish_queue (
  queue_id        TEXT PRIMARY KEY,
  story_id        TEXT NOT NULL,
  channel         TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',
  priority        INTEGER NOT NULL DEFAULT 0,
  scheduled_at    TEXT NOT NULL,
  started_at      TEXT,
  completed_at    TEXT,
  attempts        INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 5,
  last_error      TEXT,
  fb_dedupe_key   TEXT,
  backoff_seconds INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pq_dedupe
  ON publish_queue(fb_dedupe_key) WHERE fb_dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pq_status_sched
  ON publish_queue(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_pq_channel_status
  ON publish_queue(channel, status);
CREATE INDEX IF NOT EXISTS idx_pq_story_channel
  ON publish_queue(story_id, channel);
"""

DDL_FB_RATE_STATE = """
CREATE TABLE IF NOT EXISTS fb_rate_state (
  id                INTEGER PRIMARY KEY CHECK (id = 1),
  posts_this_hour   INTEGER NOT NULL DEFAULT 0,
  hour_window_start TEXT,
  posts_today       INTEGER NOT NULL DEFAULT 0,
  day_window_start  TEXT,
  last_post_at      TEXT,
  updated_at        TEXT NOT NULL
);
"""

DDL_METRICS = """
CREATE TABLE IF NOT EXISTS metrics (
  metric_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT,
  phase       TEXT NOT NULL,
  key         TEXT NOT NULL,
  value       REAL NOT NULL,
  recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_phase_key
  ON metrics(phase, key, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_run
  ON metrics(run_id);
"""

DDL_DAILY_REPORTS = """
CREATE TABLE IF NOT EXISTS daily_reports (
  report_date       TEXT PRIMARY KEY,
  report_markdown   TEXT NOT NULL,
  stories_published INTEGER NOT NULL DEFAULT 0,
  fb_posts          INTEGER NOT NULL DEFAULT 0,
  errors_total      INTEGER NOT NULL DEFAULT 0,
  generated_at      TEXT NOT NULL
);
"""

DDL_ITEM_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS item_embeddings (
  item_key   TEXT PRIMARY KEY,
  embedding  BLOB NOT NULL,
  model      TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
"""

# ─────────────────────────────────────────────────────────────────────────────
# Full ordered list of DDL statements applied by migrate.py
# ─────────────────────────────────────────────────────────────────────────────

ALL_DDL: list[str] = [
    # D1-compatible
    DDL_ITEMS,
    DDL_STORIES,
    DDL_STORY_ITEMS,
    DDL_PUBLICATIONS,
    DDL_RUNS,
    DDL_RUN_LOCK,
    DDL_ERROR_EVENTS,
    # Local-only
    DDL_SOURCE_STATE,
    DDL_IMAGES_CACHE,
    DDL_PUBLISH_QUEUE,
    DDL_FB_RATE_STATE,
    DDL_METRICS,
    DDL_DAILY_REPORTS,
    DDL_ITEM_EMBEDDINGS,
]
