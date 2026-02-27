# docs/DB_SCHEMA.md — D1 Schema Contract & Invariants

This document defines the authoritative database schema contract for D1.
The executable schema is in:
- `db/migrations/001_init.sql` (and subsequent migrations)
- `db/schema.sql` (snapshot)

This doc explains:
- tables and key fields
- uniqueness constraints that enforce idempotency
- indexes required for performance
- invariants that must remain true

---

## 1) Design goals

- **Idempotency**: repeated ingestion runs do not create duplicates.
- **Traceability**: every run is recorded; errors are attributable to run/source/phase.
- **Minimal retention**: store only necessary content snippets (truncated).
- **Publish state**: web + FB state is explicit and retry-safe.

---

## 2) Tables overview

### 2.1 `items`
Stores individual source entries (articles/materials).

Required fields:
- `item_id` (TEXT primary key; UUID/ULID string)
- `source_id` (TEXT, not null)
- `source_url` (TEXT, not null)
- `normalized_url` (TEXT, not null)
- `item_key` (TEXT, not null) — `sha256(normalized_url)`
- `title_he` (TEXT, not null)
- `published_at` (TEXT ISO8601, nullable)
- `updated_at` (TEXT ISO8601, nullable)
- `date_confidence` (TEXT enum: high|low, not null default low)
- `snippet_he` (TEXT, nullable; truncated internal snippet; **max 500 characters** enforced by code)
- `title_hash` (TEXT, nullable)
- `content_hash` (TEXT, nullable)
- `ingested_at` (TEXT ISO8601, not null)
- `status` (TEXT enum; not null default 'new')

**Uniqueness**
- `UNIQUE(item_key)` — primary dedupe invariant.

**Indexes**
- `(source_id, published_at)`
- `(ingested_at)`

---

### 2.2 `stories`
Stores one real-world event/topic.

Required fields:
- `story_id` (TEXT primary key)
- `story_key` (TEXT, nullable but recommended unique when set)
- `start_at` (TEXT ISO8601, not null)
- `last_update_at` (TEXT ISO8601, not null)
- `title_ru` (TEXT, nullable)
- `summary_ru` (TEXT, nullable)
- `summary_hash` (TEXT, nullable)
- `summary_version` (INTEGER, not null default 0)
- `category` (TEXT enum; not null default 'other')
- `risk_level` (TEXT enum; not null default 'low')
- `state` (TEXT enum; not null default 'draft')

**Indexes**
- `(last_update_at DESC)` — feed ordering
- `(state, last_update_at DESC)` — published feed fast path

**Optional uniqueness**
- If `story_key` is used, prefer `UNIQUE(story_key)`.

---

### 2.3 `story_items`
Join table linking items to stories.

Fields:
- `story_id` (TEXT, not null)
- `item_id` (TEXT, not null)
- `added_at` (TEXT ISO8601, not null)
- `rank` (INTEGER, not null default 0)

**Uniqueness**
- `UNIQUE(story_id, item_id)` — prevents duplicate attachment.

**Indexes**
- `(story_id, rank)`
- `(item_id)`

---

### 2.4 `publications`
Tracks publish state for each story (web + fb).

Fields:
- `story_id` (TEXT primary key)
- `web_status` (TEXT enum: pending|published|failed; not null default pending)
- `web_published_at` (TEXT ISO8601, nullable)
- `fb_status` (TEXT enum: disabled|pending|posted|failed|auth_error|rate_limited; not null default disabled)
- `fb_post_id` (TEXT, nullable)
- `fb_posted_at` (TEXT ISO8601, nullable)
- `fb_error_last` (TEXT, nullable, truncated)
- `fb_attempts` (INTEGER, not null default 0)

**Uniqueness / idempotency**
- One row per story (PK = story_id).
- Presence of `fb_post_id` + `fb_status=posted` means “do not repost”.

**Indexes**
- `(fb_status)`
- `(web_status)`

---

### 2.5 `runs`
One row per Cron run.

Fields:
- `run_id` (TEXT primary key)
- `started_at`, `finished_at` (TEXT ISO8601)
- `status` (TEXT enum: success|partial_failure|failure; not null)
- Counters:
  - `sources_ok`, `sources_failed`
  - `items_found`, `items_new`
  - `stories_new`, `stories_updated`
  - `published_web`, `published_fb`
  - `errors_total`
- `duration_ms` (INTEGER)
- `error_summary` (TEXT nullable, truncated)

**Indexes**
- `(started_at DESC)`

---

### 2.6 `run_lock`
Lease lock table to prevent overlapping Cron runs.

Fields:
- `lock_name` (TEXT primary key)
- `lease_owner` (TEXT run_id)
- `lease_until` (TEXT ISO8601)

**Invariant**
- If `lease_until > now`, a new run must not proceed.

---

### 2.7 `error_events`
Structured error records.

Fields:
- `event_id` (TEXT primary key)
- `run_id` (TEXT not null)
- `phase` (TEXT not null)
- `source_id` (TEXT nullable)
- `story_id` (TEXT nullable)
- `code` (TEXT or INTEGER stored as TEXT)
- `message` (TEXT truncated)
- `created_at` (TEXT ISO8601 not null)

**Indexes**
- `(run_id)`
- `(source_id, created_at DESC)`
- `(phase, created_at DESC)`

---

## 3) Enums (stored as TEXT)

**Important: SQLite does not enforce CHECK constraints on TEXT values by default.**
Enum validity is enforced entirely in application code, not by the database engine.
Every enum column must be validated before INSERT/UPDATE. Tests must cover invalid value rejection.

Enum definitions:

| Column | Valid values |
|--------|-------------|
| `items.date_confidence` | `high` \| `low` |
| `items.status` | `new` \| `existing` \| `clustered` \| `failed` \| `paywalled` |
| `stories.category` | `politics` \| `security` \| `economy` \| `society` \| `tech` \| `health` \| `culture` \| `sport` \| `weather` \| `other` |
| `stories.risk_level` | `low` \| `medium` \| `high` |
| `stories.state` | `draft` \| `published` \| `hidden` |
| `publications.web_status` | `pending` \| `published` \| `failed` |
| `publications.fb_status` | `disabled` \| `pending` \| `posted` \| `failed` \| `auth_error` \| `rate_limited` |
| `runs.status` | `success` \| `partial_failure` \| `failure` |

**Recommended CHECK constraint pattern** (add in future migration if needed):
```sql
-- Example: enforce story.state values
ALTER TABLE stories ADD CONSTRAINT chk_story_state
  CHECK (state IN ('draft', 'published', 'hidden'));
```
Note: D1 (SQLite) CHECK constraints are parsed but enforcement behavior may vary. Code-level validation remains the primary guard.

---

## 4) Critical invariants (must always hold)

### 4.1 Item dedupe invariant
- There is at most one Item per `item_key`:
  - `items.item_key` is UNIQUE.

### 4.2 Story attachment invariant
- An item can be attached to a story at most once:
  - `story_items(story_id, item_id)` UNIQUE.

### 4.3 Publication idempotency invariant
- A story has exactly one publications row:
  - PK `publications.story_id`.

### 4.4 Cron concurrency invariant
- A Cron run must not proceed when lock lease is valid:
  - `run_lock.lease_until > now` blocks new work.

### 4.5 Minimal retention invariant
- `snippet_he` must be truncated to ≤ 500 characters (enforced by code; validated by tests).
- No column stores full article text. `summary_ru` stores only the generated Russian summary (400–700 chars target).

---

## 5) Query patterns (expected)

### Feed
- Select published stories ordered by `last_update_at desc`, paginated by cursor.

### Story detail
- Select story + publications + timeline (joined story_items → items).

### Ops
- last 20 runs ordered by started_at desc.
- error_events filtered by run_id or source_id.

---

## 6) Migration policy

- All schema changes must be forward-only migrations.
- Migrations should add columns/tables/indexes; avoid dropping.
- Any destructive migration must:
  - be documented in `docs/DECISIONS.md`
  - include runbook steps and backups
