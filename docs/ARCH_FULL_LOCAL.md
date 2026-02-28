# Architecture: Full Local Engine

## Overview

All news processing runs on a local Python daemon. Cloudflare (Worker + D1 + Pages) serves as a **read-only display layer**; it receives published stories from the local engine via a sync push.

```
┌────────────────────────────────────────────────────────────────┐
│  Local Machine (Python daemon — apps/local-engine)             │
│                                                                │
│  Scheduler (10 min loop)                                       │
│    │                                                           │
│    ├─ Phase 1: RSS Ingest ──────────────────► SQLite DB        │
│    │           feedparser + httpx                              │
│    │           per-source rate limiting                        │
│    │                                                           │
│    ├─ Phase 2: Clustering ──────────────────► SQLite DB        │
│    │           Jaccard (0.25, 24h window)                      │
│    │           Hebrew tokenizer                                │
│    │                                                           │
│    ├─ Phase 3: AI Summary ──────────────────► Ollama :11434    │
│    │           qwen2.5:7b-instruct Q4_K_M                      │
│    │           guards + glossary + categories                  │
│    │                                                           │
│    ├─ Phase 4: Image Cache ─────────────────► data/images/     │
│    │           enclosure_url + og:image                        │
│    │           etag + Pillow validation                        │
│    │                                                           │
│    ├─ Phase 5: FB Publish Queue ────────────► FB Graph API     │
│    │           8/hr, 40/day, 3min gap                          │
│    │           exponential backoff                             │
│    │                                                           │
│    └─ Phase 6: CF Sync ─────────────────────► CF Worker        │
│               POST /api/v1/sync/stories                        │
│               Bearer token auth                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  Cloudflare (read-only display)                                │
│                                                                │
│  Worker (/api/v1/*)  ←── sync push ───── local engine         │
│       │                                                        │
│       ├── D1 (news_hub_prod)                                   │
│       └── Pages (Astro SSR + client polling every 60s)         │
└────────────────────────────────────────────────────────────────┘
```

## Component Map

```
apps/local-engine/
├── main.py                         # async scheduler loop
├── config/settings.py              # pydantic Settings from .env
├── db/
│   ├── schema.py                   # all CREATE TABLE DDL
│   ├── migrate.py                  # apply on startup (idempotent)
│   ├── connection.py               # aiosqlite ctx mgr (WAL + FK)
│   └── repos/                      # items, stories, story_items,
│                                   # publications, runs, errors,
│                                   # source_state, images, publish_queue
├── sources/
│   ├── models.py                   # pydantic Source model
│   └── registry.py                 # load from sources/registry.yaml
├── ingest/
│   ├── rss.py                      # feedparser RSS 2.0 + Atom
│   ├── normalize.py                # URL norm + SHA-256 (matches TS)
│   └── html_strip.py               # strip tags + entities
├── cluster/
│   ├── tokens.py                   # Hebrew tokenizer + Jaccard
│   └── cluster.py                  # cluster_new_items()
├── summary/
│   ├── ollama.py                   # Ollama /api/chat HTTP client
│   ├── prompt.py                   # system + user prompt
│   ├── glossary.py                 # Russian normalization
│   ├── guards.py                   # length, forbidden, numbers, risk
│   ├── format.py                   # 5-section parser
│   ├── categories.py               # auto-category + hashtags
│   └── generate.py                 # pipeline orchestrator
├── images/
│   ├── cache.py                    # ImageCacheManager
│   └── og_parser.py                # extract og:image
├── publish/
│   ├── facebook.py                 # FB Graph API client
│   └── queue.py                    # rate-limited publish queue
├── sync/
│   └── cf_sync.py                  # push to CF Worker
└── observe/
    ├── logger.py                   # structlog JSON
    ├── metrics.py                  # MetricsRecorder
    ├── report.py                   # daily markdown report
    └── why_not.py                  # diagnostic: why not published
```

## Data Flow Detail

### 1. RSS Ingest
- Reads `sources/registry.yaml` (8 Hebrew sources)
- Per-source scheduling: `min_interval_sec` + exponential backoff on failure
- `normalize_url()` produces the same `item_key = sha256(normalized_url)` as the TypeScript worker — **critical for D1 sync compatibility**
- `upsert_items()` uses `INSERT OR IGNORE` to deduplicate

### 2. Clustering
- Groups items into stories by Jaccard similarity of Hebrew titles
- Threshold: `> 0.25` (strict), window: 24 hours
- 73 Hebrew stopwords (identical to TS `title_tokens.ts`)
- New items either attach to an existing story or create a new draft

### 3. AI Summary
- Ollama `qwen2.5:7b-instruct` at `localhost:11434`
- ~3 seconds per summary on RTX 3070 at 116 t/s
- Memoization: `sha256(sorted(item_ids) + ':' + risk_level)` prevents re-summarizing unchanged stories
- Guards: length (400–700 chars), forbidden words, Hebrew number transliteration, high-risk content
- Glossary: normalizes military terms (ЦАХАЛvsЦАХАЛ), institutions (Кнессет), places

### 4. Image Cache
- Extracts `enclosure_url` from RSS feeds
- Falls back to `og:image` via BeautifulSoup HTML parse
- Validates with Pillow: JPEG/PNG/WebP only, ≤5 MB
- ETag support: skips re-download if content unchanged
- Stored at `data/images/{sha256[:2]}/{content_hash}.{ext}`

### 5. FB Publish Queue
- Idempotency key: `{story_id}:v{summary_version}`
- Rate limits: 8 posts/hour, 40 posts/day, 3-minute minimum gap
- Exponential backoff: `min(2^n × 60, 3600)` seconds, max 5 attempts
- Circuit breaker: FB error codes 190/102 (auth failure) → stop all posts
- Photo posts via multipart `/{page_id}/photos`

### 6. CF Sync
- Pushes all unsynced published stories in a single HTTP request
- Worker does D1 `batch()` upsert: stories + items + story_items + publications
- On success: marks `cf_synced_at` in local SQLite
- Pages frontend polls every 60 seconds and reloads on new content

## Hardware

| Component | Spec |
|-----------|------|
| CPU | Ryzen 7 PRO 3700 (8c/16t) |
| RAM | 16 GB |
| GPU | RTX 3070 8 GB VRAM |
| OS | Windows 10 Pro |
| Ollama | v0.17.4 |
| Model | qwen2.5:7b-instruct Q4_K_M |
| Speed | 116 t/s → ~3 s/summary |

## Scheduler Loop

```python
while True:
    run_id = uuid4().hex
    await start_run(db, run_id)
    # Phase 1–6 (each isolated with try/except)
    await finish_run(db, run_id, ...)
    await asyncio.sleep(interval + jitter)
```

Default interval: 600 seconds (10 minutes), jitter: 0–60 seconds.
