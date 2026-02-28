# Local SQLite Schema

All tables live in `data/news_hub.db` (path configured via `DATABASE_PATH`).
WAL mode and `PRAGMA foreign_keys=ON` are set on every connection.

## D1-Compatible Tables

These seven tables are exact copies of the Cloudflare D1 migrations so that
pushed data is accepted without transformation.

### items

Raw news articles ingested from RSS feeds.

| Column | Type | Notes |
|--------|------|-------|
| item_id | TEXT PK | sha256(normalized_url) |
| source_id | TEXT NOT NULL | e.g. "ynet", "haaretz" |
| source_url | TEXT NOT NULL | original URL from feed |
| normalized_url | TEXT NOT NULL | after UTM strip + sort |
| item_key | TEXT NOT NULL UNIQUE | sha256(normalized_url) — must match D1 |
| title_he | TEXT | Hebrew headline |
| published_at | TEXT | ISO 8601 UTC |
| date_confidence | TEXT | "high" / "estimated" / "unknown" |
| ingested_at | TEXT NOT NULL | when first seen |

### stories

Clustered story groups (one per news event).

| Column | Type | Notes |
|--------|------|-------|
| story_id | TEXT PK | uuid4().hex |
| start_at | TEXT NOT NULL | earliest item timestamp |
| last_update_at | TEXT NOT NULL | most recent item or summary update |
| category | TEXT | politics / security / economy / … |
| risk_level | TEXT | low / medium / high / critical |
| state | TEXT | draft / published |
| title_ru | TEXT | extracted from AI summary |
| summary_ru | TEXT | full Russian summary |
| summary_version | INTEGER | increments on each regeneration |
| hashtags | TEXT | JSON array of hashtag strings |
| editorial_hold | INTEGER DEFAULT 0 | 1 = paused, skip FB posting |
| cf_synced_at | TEXT | when last pushed to Cloudflare (local only) |

### story_items

Many-to-many link between stories and items.

| Column | Type | Notes |
|--------|------|-------|
| story_id | TEXT PK (part) | FK → stories |
| item_id | TEXT PK (part) | FK → items |
| added_at | TEXT NOT NULL | when item was clustered into story |

### publications

Per-story posting status per channel.

| Column | Type | Notes |
|--------|------|-------|
| story_id | TEXT PK | FK → stories |
| web_status | TEXT DEFAULT 'pending' | pending / published |
| web_published_at | TEXT | |
| fb_status | TEXT DEFAULT 'disabled' | disabled / pending / posted / failed |
| fb_post_id | TEXT | returned by Graph API |
| fb_posted_at | TEXT | when successfully posted |
| fb_error_last | TEXT | last error message |
| fb_attempts | INTEGER DEFAULT 0 | retry count |

### runs

One row per scheduler cycle.

| Column | Type | Notes |
|--------|------|-------|
| run_id | TEXT PK | |
| started_at | TEXT NOT NULL | |
| finished_at | TEXT | null while in progress |
| status | TEXT | in_progress / finished / failed |
| sources_ok | INTEGER DEFAULT 0 | |
| sources_failed | INTEGER DEFAULT 0 | |
| items_found | INTEGER DEFAULT 0 | |
| items_new | INTEGER DEFAULT 0 | |
| stories_new | INTEGER DEFAULT 0 | |
| stories_updated | INTEGER DEFAULT 0 | |
| published_web | INTEGER DEFAULT 0 | |
| published_fb | INTEGER DEFAULT 0 | |
| errors | INTEGER DEFAULT 0 | |

### run_lock

Singleton row prevents overlapping runs.

| Column | Type | Notes |
|--------|------|-------|
| lock_id | INTEGER PK CHECK(=1) | always 1 |
| run_id | TEXT NOT NULL | |
| acquired_at | TEXT NOT NULL | |
| expires_at | TEXT NOT NULL | TTL lease |

### error_events

Individual error records per run.

| Column | Type | Notes |
|--------|------|-------|
| event_id | TEXT PK | uuid4().hex |
| run_id | TEXT NOT NULL | FK → runs |
| phase | TEXT NOT NULL | ingest / cluster / summary / … |
| source_id | TEXT | nullable |
| story_id | TEXT | nullable |
| code | TEXT | error class name |
| message | TEXT | error message |
| created_at | TEXT NOT NULL | ISO 8601 UTC |

---

## Local-Only Tables

### source_state

Per-source fetch scheduling and backoff.

| Column | Type | Notes |
|--------|------|-------|
| source_id | TEXT PK | |
| last_fetch_at | TEXT | |
| last_success_at | TEXT | |
| consecutive_failures | INTEGER DEFAULT 0 | |
| backoff_until | TEXT | skip fetching until this time |
| total_fetches | INTEGER DEFAULT 0 | |
| total_items_found | INTEGER DEFAULT 0 | |
| updated_at | TEXT NOT NULL | |

### images_cache

Downloaded images for FB photo posts.

| Column | Type | Notes |
|--------|------|-------|
| image_id | TEXT PK | sha256(original_url) |
| item_id | TEXT | nullable |
| story_id | TEXT | nullable |
| original_url | TEXT NOT NULL | |
| local_path | TEXT | `data/images/{id[:2]}/{hash}.{ext}` |
| etag | TEXT | for conditional GET |
| content_hash | TEXT | sha256 of file bytes |
| width | INTEGER | |
| height | INTEGER | |
| size_bytes | INTEGER | |
| mime_type | TEXT | image/jpeg, image/png, image/webp |
| cached_at | TEXT NOT NULL | |
| status | TEXT DEFAULT 'pending' | pending / downloaded / failed |

### publish_queue

Work queue for FB (and future channel) posts.

| Column | Type | Notes |
|--------|------|-------|
| queue_id | TEXT PK | uuid4().hex |
| story_id | TEXT NOT NULL | FK → stories |
| channel | TEXT NOT NULL | fb / telegram / cf_sync |
| status | TEXT DEFAULT 'pending' | pending / in_progress / completed / failed |
| priority | INTEGER DEFAULT 0 | higher = processed first |
| scheduled_at | TEXT NOT NULL | when eligible to process |
| started_at | TEXT | |
| completed_at | TEXT | |
| attempts | INTEGER DEFAULT 0 | |
| max_attempts | INTEGER DEFAULT 5 | |
| last_error | TEXT | |
| fb_dedupe_key | TEXT | `{story_id}:v{version}` |
| backoff_seconds | INTEGER DEFAULT 0 | |
| created_at | TEXT NOT NULL | |

Unique index on `fb_dedupe_key WHERE fb_dedupe_key IS NOT NULL`.

### fb_rate_state

Singleton tracking FB posting quota windows.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK CHECK(=1) | always 1 |
| posts_this_hour | INTEGER DEFAULT 0 | |
| hour_window_start | TEXT | start of current hour window |
| posts_today | INTEGER DEFAULT 0 | |
| day_window_start | TEXT | start of current day window |
| last_post_at | TEXT | for minimum gap enforcement |
| updated_at | TEXT NOT NULL | |

### metrics

Per-run numeric metrics.

| Column | Type | Notes |
|--------|------|-------|
| metric_id | INTEGER PK AUTOINCREMENT | |
| run_id | TEXT | nullable |
| phase | TEXT NOT NULL | ingest / cluster / summary / … |
| key | TEXT NOT NULL | items_new / duration_ms / … |
| value | REAL NOT NULL | |
| recorded_at | TEXT NOT NULL | |

Indexed on `(phase, key, recorded_at DESC)` and `run_id`.

### daily_reports

Generated markdown summaries.

| Column | Type | Notes |
|--------|------|-------|
| report_date | TEXT PK | YYYY-MM-DD |
| report_markdown | TEXT NOT NULL | full markdown |
| stories_published | INTEGER DEFAULT 0 | |
| fb_posts | INTEGER DEFAULT 0 | |
| errors_total | INTEGER DEFAULT 0 | |
| generated_at | TEXT NOT NULL | |

### item_embeddings

Vector embeddings for clustering v2 (PATCH-09).

| Column | Type | Notes |
|--------|------|-------|
| item_key | TEXT PK | |
| embedding | BLOB NOT NULL | numpy array serialised to bytes |
| model | TEXT NOT NULL | e.g. "nomic-embed-text" |
| dimensions | INTEGER NOT NULL | e.g. 768 |
| created_at | TEXT NOT NULL | |
