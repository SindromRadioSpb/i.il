# docs/ROADMAP.md — News Hub (A1) Product Roadmap

## Vision

News Hub is a professional-grade, automated news aggregation and publishing system that ingests Hebrew-language news sources, clusters duplicate coverage into single authoritative "stories", generates original Russian summaries, and distributes them through a canonical website and an official Facebook Page — all without storing full copyrighted content, exposing secrets, or requiring manual editorial intervention for routine news.

---

## Milestones

### v0.1 — Skeleton & Infrastructure (PATCH-01 → 05)
*Goal: Green CI, real D1, working local dev, RSS ingestion producing Items.*

**Features**
- Monorepo scaffold (pnpm workspace, TypeScript, ESLint, Prettier, Vitest)
- GitHub Actions CI (`lint → typecheck → test`) for worker and web
- Cloudflare Worker skeleton: routing, env bindings, `GET /api/v1/health`
- D1 schema v1: `items`, `stories`, `story_items`, `publications`, `runs`, `run_lock`, `error_events`
- D1 remote database provisioned (`news_hub_dev`, WEUR)
- Sources registry (`sources/registry.yaml`) with YAML validation (Zod)
- URL normalization + `item_key = sha256(normalized_url)` dedupe primitive
- RSS ingestion MVP: fetch → parse → upsert items → record run history
- D1 lease lock for Cron idempotency (`run_lock` table)

**Non-goals**
- Story clustering (not yet)
- Russian summary generation (not yet)
- Web frontend rendering (not yet)
- Facebook crossposting (not yet)

**Acceptance highlights**
- `bash scripts/ci.sh` passes (lint + typecheck + test, worker + web)
- `pnpm -C apps/worker dev` runs without errors
- `GET /api/v1/health` returns `{ok:true, service:{...}, last_run:null}`
- `GET /api/v1/feed` returns `{ok:true, data:{stories:[], next_cursor:null}}`
- Re-running ingest does not create duplicate items (idempotency verified by test)
- D1 migration applied remotely, `sqlite_master` confirms all 7 tables

---

### v0.2 — Core Pipeline: Stories + Summaries + Web (PATCH-06 → 09)
*Goal: End-to-end flow — ingest → cluster → summarise → publish on website.*

**Features**
- Story clustering (deterministic heuristic: Jaccard token similarity + 24-hour time window)
- Story model: canonical URL, `risk_level`, `category`, state (`draft → published`)
- RU summary generation pipeline:
  - input selection (title + snippet, ≤ 2 000 chars)
  - output format: что произошло / почему важно / что дальше / источники
  - numeric guard (preserve numbers from source)
  - glossary substitution (toponyms, names)
  - memoization (hash inputs → skip regeneration if unchanged)
- Public API v1 fully implemented:
  - `GET /api/v1/feed?limit&cursor` with opaque cursor pagination
  - `GET /api/v1/story/:id` with sources + timeline
- Astro web frontend:
  - feed page (story cards with excerpt, category, timestamp)
  - story page (summary, sources, timeline, OG tags, canonical URL)
  - sitemap generation

**Non-goals**
- Facebook crossposting (not yet)
- Semantic / embedding-based clustering (deferred, behind feature flag)
- Human review queue (deferred)
- Multi-channel publishing (deferred)

**Acceptance highlights**
- One real-world event → one story with RU summary in correct format
- No duplicate stories across re-runs
- Web feed renders with correct canonical URLs and OG tags
- `astro check` passes with 0 errors
- Summary-only: no full source text in public pages

---

### v1.0 — Hardening + Facebook + Ops (PATCH-10 → 12 → RC1)
*Goal: Production-ready, observable, Facebook-connected, demo-ready.*

**Features**
- Cron hardening:
  - per-source `min_interval_sec` throttling
  - exponential backoff on 429/503 with `Retry-After` support
  - `max_items_per_run` and per-source caps enforced
  - run time budget (< 30 s, graceful stop)
- Facebook crossposting v1:
  - official Graph API for our own Page only
  - no scraping, no browser automation
  - idempotent: stores `fb_post_id`, prevents duplicate posts
  - error mapping: `auth_error` (401/403), `rate_limited` (429), bounded retry
- Ops polish:
  - `GET /api/v1/health` full payload: last run status + counters
  - optional ops page (non-sensitive, run history)
  - `docs/DEMO.md` — 2-minute wow-demo script
- Documentation finalized: ACCEPTANCE.md satisfied, RUNBOOK.md complete

**Non-goals**
- Telegram / WhatsApp publishing (post-v1)
- Embeddings clustering (post-v1, behind feature flag)
- Multi-region D1 (post-v1)

**Acceptance highlights**
- Scenario A (50 items/day): Cron run < 30 seconds
- `docs/ACCEPTANCE.md` checklist: all items pass
- Facebook: one story → one post, no duplicates across runs
- Run history visible in health endpoint
- `bash scripts/ci.sh` fully green (all worker + web gates)
- Compliance: summary-only, attribution present, no FB scraping confirmed by tests

---

## Engineering Checklist

This checklist applies to every milestone before it is marked complete.

### Tests
- [ ] Unit tests pass for all changed modules (`pnpm -C apps/worker test`)
- [ ] Web tests pass (`pnpm -C apps/web test`)
- [ ] Regression tests added for any bug fix
- [ ] New business-logic paths have at least one positive + one negative test

### Observability
- [ ] Structured logs use correlation IDs (`run_id`, `source_id`, `story_id`)
- [ ] No secrets or full article bodies in logs
- [ ] Run counters recorded in `runs` table
- [ ] Error events recorded in `error_events` table

### Compliance (see `docs/COMPLIANCE.md`)
- [ ] Only original RU summaries published (no full source text)
- [ ] Attribution and source links present on every story
- [ ] No Facebook scraping or browser automation
- [ ] No secrets committed to repo or logs
- [ ] Sensitive topics use neutral phrasing and ≥ 2 sources

### Security (see `docs/SECURITY.md`)
- [ ] No SSRF exposure (arbitrary URL fetch)
- [ ] No SQL concatenation with user input
- [ ] Admin endpoints disabled by default in prod
- [ ] Tokens managed via Cloudflare secrets / env only

### Quality Gates (see `docs/QUALITY_GATES.md`)
- [ ] `bash scripts/ci.sh` green
- [ ] D1 migrations forward-only and applied cleanly
- [ ] API contract updated if endpoints changed
- [ ] DECISIONS.md updated for architectural choices
