# docs/IMPLEMENTATION_PLAN.md — Autonomous Build Plan (PATCH series)

This plan is written so Claude Code can implement the entire project autonomously in small, safe increments.
Each patch includes: **goal**, **files**, **patch steps**, **tests**, and **DoD**.

Assumptions:
- Stack A1: Cloudflare Pages + Workers (Cron) + D1
- Language: TypeScript end-to-end
- Package manager: pnpm workspace (monorepo)
- Testing: Vitest
- Lint/format: ESLint + Prettier
- Web framework: Astro (recommended for SEO + simplicity) **or** Next.js.
  - Default in this plan: **Astro** (can be swapped later with a single decision update).

Non-negotiables:
- Summary-only + attribution (COMPLIANCE)
- No Facebook scraping
- Idempotent Cron + D1 lease lock
- No secrets in repo/logs
- Migration-driven schema

---

## 0) Milestones

- **M0 (Repo bootstrap):** Workspace, tools, CI green.
- **M1 (Data layer):** D1 schema + migrations + DAO.
- **M2 (Ingestion MVP):** RSS ingest + dedupe + run history.
- **M3 (Stories MVP):** clustering heuristics + story API.
- **M4 (RU summaries):** summary generation pipeline + guards + formatting.
- **M5 (Web frontend):** feed + story pages + SEO tags.
- **M6 (Cron hardening):** lock/lease, backoff, source throttling, stability.
- **M7 (Facebook crosspost):** official posting + idempotency + error mapping.
- **M8 (Ops polish):** health endpoint + run dashboard + docs finalization.
- **RC1:** acceptance checklist passes; demo flow ready.

---

## PATCH-01: Monorepo scaffolding (pnpm workspace) + toolchain

### Goal
Create a minimal, buildable workspace with `apps/worker` and `apps/web`, consistent TS settings, and basic scripts.

### Files
- `package.json` (root)
- `pnpm-workspace.yaml`
- `pnpm-lock.yaml` (generated)
- `tsconfig.base.json`
- `apps/worker/package.json`
- `apps/web/package.json`
- `scripts/ci.sh` (optional)
- `.github/workflows/ci.yml` (fix if needed)

### Patch steps
1) Initialize pnpm workspace with two packages: `apps/worker`, `apps/web`.
2) Add shared TS base config (`tsconfig.base.json`).
3) Add root scripts:
   - `lint`, `typecheck`, `test` calling subpackages
4) Ensure CI uses Node 20 and `pnpm install --frozen-lockfile`.

### Tests
- `pnpm -C apps/worker typecheck` (should pass even with empty src)
- `pnpm -C apps/web typecheck`

### DoD
- `pnpm install` works
- CI pipeline runs without YAML errors
- Both packages build/typecheck with placeholder src

---

## PATCH-02: Worker skeleton (Wrangler + routing + D1 binding stub)

### Goal
Create a Cloudflare Worker app with minimal routing and environment bindings.

### Files
- `apps/worker/wrangler.toml`
- `apps/worker/src/index.ts`
- `apps/worker/src/router.ts`
- `apps/worker/src/env.ts`
- `apps/worker/tsconfig.json`

### Patch steps
1) Add Wrangler config with:
   - name, main, compatibility_date
   - D1 binding name (e.g., `DB`)
   - cron triggers placeholder (disabled by env)
2) Implement minimal router:
   - `GET /api/health` returns `{ok:true}`
3) Implement env validation:
   - `CRON_ENABLED`, `FB_POSTING_ENABLED`, `ADMIN_ENABLED`

### Tests
- Unit test: router returns health response
- `pnpm -C apps/worker test`

### DoD
- `pnpm -C apps/worker dev` runs locally
- `GET /api/health` works

---

## PATCH-03: D1 schema v1 (migrations + schema snapshot) + local apply workflow

### Goal
Implement the initial D1 schema and migration workflow.

### Files
- `db/migrations/001_init.sql`
- `db/schema.sql`
- `apps/worker/src/db/schema.ts` (table names + helpers)
- `apps/worker/src/db/migrate.ts` (local-only helper)
- `apps/worker/src/db/client.ts`

### Patch steps
1) Create `001_init.sql` with tables:
   - sources (optional mirror)
   - items
   - stories
   - story_items
   - publications
   - runs
   - run_lock
   - error_events
2) Add required unique constraints:
   - items.item_key UNIQUE
   - publications.story_id UNIQUE
   - story_items(story_id,item_id) UNIQUE
3) Add indexes for query patterns:
   - stories(last_update_at)
   - items(source_id, published_at)
4) Implement minimal DB client wrapper around D1.
5) Document local migration steps in README (short section).

### Tests
- Unit test: migration SQL contains required tables/constraints (string checks)
- Integration test (local D1 via wrangler) optional, but at least unit checks.

### DoD
- Schema is migration-driven
- DB client can execute a simple query in dev mode (smoke)

---

## PATCH-04: Sources registry loader + URL normalization primitives

### Goal
Load `sources/registry.yaml` and provide strict URL normalization + hashing utilities.

### Files
- `apps/worker/src/sources/registry.ts`
- `apps/worker/src/sources/types.ts`
- `apps/worker/src/normalize/url.ts`
- `apps/worker/src/normalize/hash.ts`
- `apps/worker/test/url_normalization.test.ts`
- `apps/worker/test/registry_loader.test.ts`

### Patch steps
1) Define source schema types and validate YAML (zod).
2) Load YAML as an asset (bundled).
3) Implement URL normalization rules from SPEC.
4) Implement stable hashing:
   - `item_key = sha256(normalized_url)`
   - `title_hash` helper

### Tests
- URL normalization cases for tracking params and host rules
- YAML validation tests with sample registry

### DoD
- Registry load is deterministic and validated
- URL normalization is stable and well-tested

---

## PATCH-05: RSS ingestion MVP (items only) + run history + error isolation

### Goal
Fetch RSS sources, create/update Items idempotently, and record run stats and errors.

### Files
- `apps/worker/src/cron/ingest.ts`
- `apps/worker/src/cron/run_lock.ts`
- `apps/worker/src/ingest/rss.ts`
- `apps/worker/src/db/items_repo.ts`
- `apps/worker/src/db/runs_repo.ts`
- `apps/worker/src/db/errors_repo.ts`

### Patch steps
1) Implement lease lock in D1:
   - acquire lock with TTL (8 minutes)
   - exit if lock is held
2) Implement RSS fetch + parse (fast XML parser).
3) For each entry:
   - normalize URL
   - upsert Item by item_key
4) Record run counters:
   - sources_ok, sources_failed, items_found, items_new
5) Record per-source errors; continue other sources.

### Tests
- Mock fetch to return RSS fixture
- Verify items inserted and not duplicated on re-run
- Verify errors recorded for one failing source

### DoD
- Cron ingestion produces Items and run history reliably
- No duplicates on rerun

---

## PATCH-06: Story model + deterministic clustering (heuristic)

### Goal
Cluster new Items into Stories and support updating Stories when new Items arrive.

### Files
- `apps/worker/src/cluster/cluster.ts`
- `apps/worker/src/db/stories_repo.ts`
- `apps/worker/src/db/story_items_repo.ts`
- `apps/worker/src/normalize/title_tokens.ts`

### Patch steps
1) Implement title tokenization (hebrew-safe, stopwords list).
2) Implement Jaccard similarity with threshold and time window.
3) For each new item:
   - find candidate story within window
   - match → attach item, update story.last_update_at
   - else → create story and attach
4) Ensure deterministic ordering of story timeline.

### Tests
- Match/no-match cases
- Window boundary cases
- Deterministic tie-breaking for candidate selection

### DoD
- One event → one story
- Stable behavior across reruns

---

## PATCH-07: Public API v1 (feed + story detail) + pagination

### Goal
Expose read-only endpoints used by the web.

### Files
- `apps/worker/src/api/feed.ts`
- `apps/worker/src/api/story.ts`
- `apps/worker/src/api/health.ts` (expand)
- `docs/API_CONTRACT.md`

### Patch steps
1) Implement:
   - `GET /api/feed?limit&cursor`
   - `GET /api/story/:id`
   - `GET /api/health` includes last run summary
2) Define cursor pagination (opaque cursor: last_update_at + story_id).
3) Update API contract doc with exact schemas.

### Tests
- Contract tests for endpoints (shape validation)
- Pagination order and cursor behavior

### DoD
- Web can be built against stable API
- `/api/health` is safe (no secrets)

---

## PATCH-08: RU summary generation v1 (format + guards + memoization)

### Goal
Generate Russian summaries for Stories, enforce format, and implement basic numeric guard and glossary application.

### Files
- `apps/worker/src/summary/generate.ts`
- `apps/worker/src/summary/format.ts`
- `apps/worker/src/summary/guards.ts`
- `apps/worker/src/summary/glossary.ts`
- `apps/worker/src/db/summaries_repo.ts`
- `docs/EDITORIAL_STYLE.md` (may update)
- `docs/GLOSSARY.md` (may update)

### Patch steps
1) Choose provider abstraction:
   - `translate(text, from, to)` and/or `summarize(inputs)`
2) Input selection:
   - take titles + short snippets (truncate)
3) Apply glossary substitutions.
4) Build RU summary strictly in required sections.
5) Numeric guard:
   - extract numbers from source snippet
   - ensure they appear in RU output; else degrade to safe minimal summary
6) Memoization:
   - hash key per story inputs → reuse previous summary if unchanged

### Tests
- Format test ensures all sections exist
- Numeric guard test
- Memoization test (same inputs → same output without provider call)

### DoD
- Summaries are stable, compliant, and cheap
- No full source text output

---

## PATCH-09: Web frontend (Astro) feed + story pages + SEO

### Goal
Create Pages frontend consuming the Worker API.

### Files
- `apps/web/` (Astro project)
- `apps/web/src/pages/index.astro`
- `apps/web/src/pages/story/[id].astro` (or slug scheme)
- `apps/web/src/lib/api.ts`
- `apps/web/test/seo.test.ts`

### Patch steps
1) Scaffold Astro app.
2) Implement feed page:
   - story cards: title, excerpt, category, timestamp
3) Implement story page:
   - summary, sources, timeline
4) Add canonical + OG tags.
5) Add sitemap generation (simple route).

### Tests
- Render tests with mocked API
- SEO tag presence tests

### DoD
- Web renders feed + story
- SEO tags and canonical URLs correct

---

## PATCH-10: Cron hardening (backoff, throttle, caps, time budgets)

### Goal
Make Cron robust under real-world failures and spikes.

### Files
- `apps/worker/src/cron/budget.ts`
- `apps/worker/src/net/fetch_with_backoff.ts`
- `apps/worker/src/cron/limits.ts`
- `docs/RUNBOOK.md` (update)

### Patch steps
1) Add fetch wrapper with timeout, Retry-After support, exponential backoff.
2) Enforce per-source `min_interval_sec`.
3) Enforce caps:
   - max new items per run
   - max items per source per run
4) Add run duration budget (e.g., 25 seconds for scenario A) with graceful stopping.

### Tests
- Backoff behavior with mocked 429/503
- Caps enforced
- Budget stop leaves run in partial state safely

### DoD
- Cron runs stable and bounded
- Partial failures recorded

---

## PATCH-11: Facebook crossposting v1 (official API) + idempotency

### Goal
Post story summaries to our Facebook Page, idempotently, with robust error mapping.

### Files
- `apps/worker/src/fb/post.ts`
- `apps/worker/src/fb/types.ts`
- `apps/worker/src/db/publications_repo.ts` (expand)
- `docs/API_CONTRACT.md` (if needed)
- `docs/RUNBOOK.md` (fb section)

### Patch steps
1) Implement Graph API client (minimal).
2) Compose FB post text (short title + bullets + canonical link).
3) Post only when:
   - `FB_POSTING_ENABLED=true`
   - publication not yet posted
4) Map errors:
   - 401/403 → auth_error, stop further attempts this run
   - 429 → rate_limited, one retry then stop
5) Store `fb_post_id` and timestamps.

### Tests
- Mock FB API success → stores fb_post_id
- Rerun does not repost
- 401/403 sets auth_error
- 429 triggers bounded retry

### DoD
- One story → one FB post
- No duplicates and failures observable

---

## PATCH-12: Ops polish (health payload, optional ops page, evidence docs)

### Goal
Make the project impressive and easy to operate/demonstrate.

### Files
- `apps/worker/src/api/health.ts` (final)
- `apps/web/src/pages/ops.astro` (optional, gated)
- `docs/OBSERVABILITY.md` (final updates)
- `docs/ACCEPTANCE.md` (final)
- `docs/DEMO.md` (new)

### Patch steps
1) `GET /api/health` returns:
   - last run status
   - last run counters
   - top failing sources in last 24h (optional)
2) Optional ops page (non-sensitive) showing last 20 runs.
3) Add `docs/DEMO.md` (2-minute wow script).

### Tests
- health endpoint contract test
- ops page render test (if added)

### DoD
- WOW demo is ready
- acceptance checklist passes

---

## PATCH-13: Documentation & skills completion (Claude autonomy pack)

### Goal
Finalize remaining docs and skills so Claude Code can proceed autonomously.

### Files
- `docs/API_CONTRACT.md` (already created earlier in patches)
- `docs/DB_SCHEMA.md` (ERD + invariants)
- `docs/SOURCE_PARSING_GUIDE.md`
- `docs/QUALITY_GATES.md`
- `.agents/skills/*/SKILL.md`

### Patch steps
1) Write the missing docs.
2) Implement skills with command recipes and anti-patterns.

### Tests
- Docs lint (optional)
- Ensure repo structure matches AGENTS/README

### DoD
- Claude Code can implement new features without needing extra clarifications.

---

## RC1 Acceptance (final)
RC1 is acceptable when `docs/ACCEPTANCE.md` is fully satisfied and:
- scenario A (50/day) runs < 30s locally
- ingestion idempotent + clustering works on fixtures
- summaries follow editorial format + guards
- web SEO correct
- FB crossposting idempotent (if enabled)
- run history and health endpoint usable
- CI green
