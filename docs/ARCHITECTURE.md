# docs/ARCHITECTURE.md — System Overview (A1: Cloudflare Pages + Workers Cron + D1)

## 1) High-level overview

This system is a **news content hub** (canonical source of truth) for Hebrew → Russian news summaries.

**Primary flow:**
Hebrew sources (RSS/sitemap/html) → ingest → normalize/dedupe → cluster into Story → generate RU summary → publish to Hub → crosspost to Facebook → analytics/run history.

Key properties:
- **Idempotent automation** (Cron-safe, retry-safe)
- **Summary-only** publication with attribution (compliance-first)
- **Cost-aware** translation (short inputs + memoization)
- **Observability** (run_id, per-source stats, persistent run history)

---

## 2) Components

### 2.1 Cloudflare Worker (apps/worker)
Responsibilities:
- Public **read-only API** for the web frontend:
  - feed list, story detail, health
- **Cron ingestion pipeline**:
  - fetch sources with throttling
  - parse entries and create/update Items
  - dedupe Items
  - cluster Items into Stories
  - generate/update RU summaries
  - publish state transitions
  - crosspost to Facebook (optional)
- **Admin endpoints (dev-only)** for manual runs and rebuilds

Key non-functional duties:
- Rate limiting & backoff
- Structured logging with correlation IDs
- Defensive error handling so one source cannot break a run

### 2.2 Cloudflare D1 (db)
Responsibilities:
- Durable state store:
  - sources snapshot (optional mirror of registry)
  - items
  - stories
  - story-item relations
  - summaries
  - publication states (web + FB)
  - cron runs, locks, errors, counters
- Enforces uniqueness constraints (dedupe)
- Provides transactional updates for state transitions

### 2.3 Cloudflare Pages (apps/web)
Responsibilities:
- SEO-first frontend:
  - feed page
  - story page
  - OG + canonical tags
  - sitemap
- Uses Worker read-only API (no secrets in the browser)

### 2.4 External services
- **Translation provider** (default: Google Cloud Translate or equivalent)
- **Facebook Pages API** (posting to our own Page only)

---

## 3) Data model (conceptual)

### 3.1 Entities

**Source**
- `source_id` (stable, from `sources/registry.yaml`)
- `type` (rss/sitemap/html)
- `url`
- `enabled`
- `throttle` config
- `parser` hints
- `category_hints`

**Item**
Represents one candidate news material (article/post) from a source.
- `item_id` (internal)
- `source_id`
- `source_url` (original)
- `normalized_url`
- `item_key = sha256(normalized_url)` (unique)
- `title_he`
- `published_at`, `updated_at`, `date_confidence`
- `snippet_he` (internal processing snippet, truncated)
- `title_hash`, `content_hash` (optional)
- `ingested_at`
- `status` (new/clustered/failed/paywalled/etc.)

**Story**
Represents one real-world event/topic, grouping multiple Items.
- `story_id` (internal)
- `story_key` (derived clustering key; stable across runs)
- `start_at`, `last_update_at`
- `best_title_he` (optional), `best_title_ru`
- `category` (single) + `category_confidence`
- `risk_level` (low/medium/high)
- `summary_ru` + metadata (`summary_version`, `summary_hash`)
- `state` (draft/published/hidden)

**StoryItem**
Join table linking items into stories:
- `story_id`
- `item_id`
- `added_at`
- `rank` (order in timeline)
- `is_primary` (optional)

**Publication**
Tracks where and how a Story was published.
- `story_id`
- `web_status` (pending/published/failed)
- `web_published_at`
- `fb_status` (disabled/pending/posted/failed/auth_error/rate_limited)
- `fb_post_id`
- `fb_posted_at`
- `fb_error_last`

**Run**
One Cron run execution record:
- `run_id` (uuid or ulid)
- `started_at`, `finished_at`
- `status` (success/partial_failure/failure)
- counters: `sources_ok`, `sources_failed`, `items_found`, `items_new`, `stories_new`, `stories_updated`, `published_web`, `published_fb`
- `error_summary` (short)

**RunLock**
Prevents overlapping Cron runs:
- `lock_name` (e.g., `cron_ingest`)
- `lease_owner` (run_id)
- `lease_until` (timestamp)

**ErrorEvent**
Per-source or per-operation error record:
- `run_id`
- `source_id` (nullable)
- `story_id` (nullable)
- `phase` (fetch/parse/cluster/translate/publish_fb/...)
- `code` (http_status or internal)
- `message` (truncated)
- `created_at`

---

## 4) Control flows

### 4.1 Cron ingestion flow (every 10 minutes)

1) **Acquire lock**
- Attempt to acquire `RunLock` with TTL (e.g., 8 minutes).
- If already locked and lease valid → exit gracefully.

2) **Load sources registry**
- Read `sources/registry.yaml` at build-time (preferred) or fetch from KV/asset.
- Filter `enabled:true`.

3) **Fetch + parse per source**
For each source:
- enforce `min_interval_sec` between requests
- fetch RSS/sitemap/html
- parse candidate entries (URL + title + date)

4) **Normalize + dedupe**
For each candidate:
- normalize URL → `normalized_url`
- compute `item_key`
- upsert Item by `item_key` (unique)
- mark as `new` if inserted, else `existing`

5) **Cluster new items**
- For each new Item:
  - compute title tokens/signals
  - find candidate Story in time window
  - if match → attach item to existing Story and mark story updated
  - else → create new Story and attach

6) **Generate/refresh RU summary**
- For new Stories: generate summary
- For updated Stories: optionally refresh summary if “breaking” or enough new info

7) **Publish to web**
- Mark Story as `published`
- Web frontend reads via API, so “publish” is a state switch

8) **Crosspost to Facebook**
- If enabled:
  - check `fb_status`
  - if not posted yet → create FB post referencing canonical URL
  - store `fb_post_id` and status

9) **Record run stats**
- Update Run record counters and status
- Release lock (or let TTL expire)

**Idempotency points:**
- unique `item_key`
- unique `story_key` (or deterministic matching)
- `Publication.fb_post_id` prevents duplicate FB posting

---

### 4.2 User-facing read flow (web)

1) Pages frontend requests feed:
- `GET /api/feed?limit=20&cursor=...`

2) Worker queries D1:
- fetch published stories, sorted by `last_update_at desc`
- returns cards: title_ru, summary excerpt, category, timestamps, canonical URL

3) For story page:
- `GET /api/story/{story_id}`
- returns full RU summary, sources list, item timeline

SEO:
- Pages renders OG tags from API response
- Canonical URL is stable and unique per story

---

## 5) Observability (signals)

### 5.1 Log fields (minimum)
- `run_id`
- `phase`
- `source_id` (if relevant)
- `item_id`, `story_id` (if relevant)
- `status` (ok/fail)
- `duration_ms`
- `err_code`, `err_msg` (truncated)

### 5.2 Persistent run history
Each Cron run writes:
- aggregate counters
- per-source errors
- a short summary for dashboards / runbook

---

## 6) Reliability & safety

### 6.1 Failure isolation
- Per-source errors do not abort the entire run.
- Crossposting failures do not block web publishing.

### 6.2 Backoff policy
- Sources: respect 429/503 and `Retry-After`
- Translation/Facebook: exponential backoff, capped retries per run (default 3)

### 6.3 Data retention
- Store minimal necessary snippet for processing.
- Do not store full article text unless explicitly required (default: **no**).
- Truncate stored snippets and logged fragments.

---

## 7) Deployment shapes

### 7.1 Environments
- `dev` (local wrangler)
- `staging` (optional)
- `prod`

### 7.2 Configuration
- Secrets via Wrangler secrets
- Non-secrets via Wrangler vars / env

---

## 8) Extension points (planned)

- Semantic clustering (embeddings) behind a feature flag
- Multi-channel publishing (Telegram/WhatsApp) using the same Publication state model
- Editorial style profiles (A/B) controlled by Growth agent
- Lightweight admin UI for manual review of `risk_level=high` stories (optional)

---

## 9) Architecture invariants (must remain true)

1) Website is canonical; social posts link back.
2) Summary-only; never publish full copyrighted article text.
3) No Facebook scraping; only official posting to our Page.
4) Cron is idempotent; reruns do not create duplicates.
5) D1 schema changes are migration-driven.
6) Secrets never leak into repo or logs.
