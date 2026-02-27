# docs/TEST_PLAN.md — Test Strategy & Coverage

This plan defines the required automated tests and CI gates for the A1 system:
**Cloudflare Pages + Workers Cron + D1** with ingestion, clustering, RU summary generation, and Facebook crossposting.

Goal: prevent regressions, prove compliance, and keep the project “portfolio-grade”.

---

## 1) Test pyramid (what we optimize for)

1) **Unit tests (fast, many):**
   - URL normalization and hashing
   - parsing primitives (RSS/sitemap/html)
   - dedupe logic and constraints
   - clustering match/no-match logic
   - summary formatting and guards (numbers/dates)
   - risk bucket classification rules

2) **Integration tests (medium):**
   - end-to-end pipeline on mocked networks:
     ingest → items → stories → publish state → crosspost state
   - D1 interaction with a local test DB (or an in-memory adapter if used)
   - worker route handlers (API contract tests)

3) **UI/web tests (targeted):**
   - feed rendering
   - story page rendering
   - OG/canonical tags correctness
   - contract compatibility with API responses

4) **E2E smoke (optional, minimal):**
   - run local worker + web against a small fixture set
   - only for release candidates (not every commit)

---

## 2) Required CI gates (must pass)

For every PR:
- `apps/worker`: lint + typecheck + tests
- `apps/web`: lint + typecheck + tests

Minimum commands (canonical):
- `pnpm -C apps/worker lint`
- `pnpm -C apps/worker typecheck`
- `pnpm -C apps/worker test`
- `pnpm -C apps/web lint`
- `pnpm -C apps/web typecheck`
- `pnpm -C apps/web test`

---

## 3) Worker tests (apps/worker)

### 3.1 Unit tests — normalization & hashing
**Target:** pure functions (no I/O).
Coverage:
- URL normalization removes tracking params:
  - `utm_*`, `fbclid`, `gclid`, `yclid`, `ref`, `ref_src`
- Host/scheme normalization
- Trailing slash normalization rules
- `item_key = sha256(normalized_url)` stability
- Title normalization for `title_hash` stability
- Text normalization for `content_hash` stability (if used)

**Must-have cases:**
- same URL with different tracking → same key
- http vs https normalization (if enabled) → stable behavior
- www vs non-www behavior (consistent)

### 3.2 Unit tests — parsing primitives
**RSS:**
- parse feed with title/link/published
- handle missing date → date_confidence=low
- malformed XML → error captured, does not crash whole run

**Sitemap:**
- parse urlset (loc + lastmod)
- large sitemap → respects `max_items_per_run`

**HTML (if used):**
- parse list page entries by selector
- parse article page content by selector
- paywall/empty content → content_confidence=low

Use fixtures stored in:
- `apps/worker/test/fixtures/rss/*.xml`
- `apps/worker/test/fixtures/sitemap/*.xml`
- `apps/worker/test/fixtures/html/*.html`

### 3.3 Unit tests — dedupe
Coverage:
- upsert behavior by `item_key`
- does not create duplicates on repeated ingest
- secondary heuristic behavior (title_hash + time window), if implemented

### 3.4 Unit tests — clustering
Coverage:
- match: similar tokens within time window → same story
- no-match: dissimilar tokens → new story
- boundary: near-threshold similarity
- window: same tokens but outside window → new story
- hard separators (if defined): explicit city/person mismatch prevents clustering

### 3.5 Unit tests — summary format & guards
Coverage:
- output always contains required sections (Title/What/Why/Next/Sources)
- length constraints (summary body 400–700 chars target; allow slight variance)
- numeric guard:
  - numbers appearing in source snippet appear in RU output
  - percent and currency formats preserved
- date guard:
  - Hebrew dates/times are converted to RU format (implementation dependent)
- risk bucket behavior:
  - `high` stories contain “по данным источников”
  - no emotional markers (as per policy, enforce minimal list)

### 3.6 Integration tests — pipeline end-to-end (mocked I/O)
Use a fake network layer:
- fetch source feed (fixture)
- fetch article pages (fixture)

Then run:
- ingestion
- dedupe
- clustering
- summary generation
- publishing state transitions
- crosspost state transitions (mock FB API)

Verify:
- correct counts: items_new, stories_new, stories_updated
- no duplicates after re-run
- publication states updated correctly
- errors recorded for failing sources but run continues

### 3.7 Integration tests — Facebook crosspost idempotency
Mock FB API:
- first call returns `fb_post_id`
- second call should not post again when status is posted
- failure case:
  - 401/403 sets `auth_error` and blocks further attempts this run
  - 429 triggers one retry with backoff and then records failure

### 3.8 API contract tests
Test:
- `GET /api/feed` returns stable schema (required fields)
- `GET /api/story/:id` returns stable schema
- `GET /api/health` returns non-sensitive status

Validate:
- no secrets in responses
- story URLs are canonical and stable

---

## 4) Web tests (apps/web)

### 4.1 Rendering tests
- Feed page renders story cards from mocked API.
- Story page renders summary + sources + timeline.

### 4.2 SEO tests
- canonical link exists and matches story URL
- OG tags exist and are consistent:
  - og:title
  - og:description
  - og:url

### 4.3 Contract compatibility
- If the web uses a typed client, verify types match the worker response schema.
- Snapshot or schema checks allowed (keep stable).

---

## 5) Manual test checklist (release candidate)

Run locally:
1) Start worker dev server.
2) Start web dev server.
3) Trigger a manual ingestion run (dev-only admin endpoint).
4) Verify:
   - feed updates with new story
   - story page shows correct RU summary and sources
   - run history shows counts and no fatal errors
5) If FB enabled:
   - post appears exactly once
   - DB shows fb_post_id
   - re-run does not duplicate the post

---

## 6) Performance sanity tests (non-flaky)

For scenario A (50 items/day):
- ingestion run duration < 30s (local baseline)
- D1 query count does not scale per-row (no N+1 patterns)
- max items per run enforced

These are measured via:
- log durations
- optional “benchmark mode” (if implemented)

---

## 7) Regression policy

- Any bug fix must come with a regression test.
- Any change to URL normalization/dedupe/clustering must include:
  - new unit tests + fixtures (if parsing changed)
  - an integration test covering the changed behavior

---

## 8) Test ownership & updates

- Worker tests live in `apps/worker/test/`.
- Web tests live in `apps/web/test/` (or framework standard).
- Fixtures are immutable once added; if source formats change, add new fixtures.

---

## 9) Exit criteria (“tests are sufficient”)

The test plan is satisfied when:
- CI gates are green for worker and web.
- Critical behaviors are covered:
  - idempotent ingest
  - dedupe keys stable
  - clustering correct on fixtures
  - summary format and safety guards
  - FB crosspost idempotency
  - SEO tags and canonical URLs
- Manual release checklist passes for a sample run.
