# docs/SOURCE_PARSING_GUIDE.md — Sources, Parsing & Fixtures

This guide explains how to add and maintain sources safely and deterministically.
Goal: make ingestion reliable, testable, and compliant.

---

## 1) Source registry (sources/registry.yaml)

### 1.1 Source entry checklist
Every source must define:
- `id` (stable snake_case)
- `name` (human readable)
- `type`: `rss` | `sitemap` | `html`
- `url` (start URL)
- `lang: he`
- `enabled: true|false`
- `throttle`:
  - `min_interval_sec` (≥ 10 recommended)
  - `max_items_per_run` (10–30 typical)
- Optional:
  - `parser` hints (selectors/strategies)
  - `category_hints`

### 1.2 Throttle policy
- Respect `min_interval_sec`. Do not hammer sources.
- Respect source terms and robots guidance.
- Backoff on 429/503 and honor `Retry-After`.

---

## 2) URL normalization (mandatory)

Normalization rules must match `docs/SPEC.md`:

- Remove tracking params:
  - `utm_*`, `fbclid`, `gclid`, `yclid`, `ref`, `ref_src`
- Lowercase scheme + host.
- Remove trailing slash (except root).
- Optionally remove leading `www.` consistently.

**Dedupe key:**
- `item_key = sha256(normalized_url)` (unique).

**Secondary dedupe heuristic (recommended):**
- `title_hash + time window` (2 hours) to catch same content under multiple URLs.

---

## 3) Parsing per source type

### 3.1 RSS / Atom parsing
Inputs:
- XML feed containing items/entries.

Extract:
- `url` (link)
- `title_he`
- `published_at` (best effort)
- optionally `updated_at`
- optionally a short snippet (description)

Rules:
- If date missing: set `date_confidence=low` and `published_at=now` (store reason if you have a field).
- If XML malformed: record a source-level error, do not crash run.

Fixtures:
- Store RSS fixtures under `apps/worker/test/fixtures/rss/<source>.xml`.

Tests:
- parsing creates expected number of entries.
- missing date handled.
- malformed feed produces parse error record.

---

### 3.2 Sitemap parsing
Inputs:
- XML `urlset` with `<loc>` and optional `<lastmod>`.

Extract:
- `url`
- `updated_at` from `<lastmod>` if present

Rules:
- Sitemaps can be huge: respect `max_items_per_run` and preferably only take newest URLs first if lastmod is available.

Fixtures:
- `apps/worker/test/fixtures/sitemap/<source>.xml`

Tests:
- parses loc/lastmod
- caps respected

---

### 3.3 HTML parsing (only when needed)
HTML parsing has higher fragility. Prefer RSS/sitemap when possible.

Two patterns:
1) **Listing page** → extract article URLs
2) **Article page** → extract title/snippet (optional)

Rules:
- Do not bypass paywalls.
- Limit response size and parse defensively.
- Never expose raw HTML publicly.

Selectors:
- defined in `sources/registry.yaml` under `parser.*`.

Fixtures:
- `apps/worker/test/fixtures/html/<source>_list.html`
- `apps/worker/test/fixtures/html/<source>_article.html`

Tests:
- selectors extract expected URLs/titles
- paywall/empty content → content_confidence=low and no crashes

---

## 4) Paywalls and unavailable content

If content is paywalled or inaccessible:
- Do not attempt bypass.
- Store minimal metadata: title + link.
- Mark `content_confidence=low`.
- Summary must rely only on accessible text (title/snippet).

---

## 5) Error recording requirements

On errors, record an `error_event` with:
- `run_id`
- `phase`: fetch|parse|...
- `source_id`
- `code`: http status or internal code
- `message`: truncated

And continue with other sources.

---

## 6) Adding a new source — step-by-step

1) Add entry to `sources/registry.yaml`
2) Add fixture file(s) for the source type
3) Add or update parser implementation (if needed)
4) Add tests:
   - parsing correctness
   - normalization/dedupe
   - caps and throttle behavior (where applicable)
5) Run full gate:
   - `pnpm -C apps/worker lint && pnpm -C apps/worker typecheck && pnpm -C apps/worker test`
6) Submit PR with:
   - description of source
   - expected categories
   - known limitations

---

## 7) Determinism requirements (avoid flakiness)

- Sort entries deterministically (by date desc, then URL).
- When applying caps, apply after deterministic sorting.
- Normalize URLs before hashing.
- For tie-breaking (clustering candidates), use stable ordering:
  - last_update_at desc, then story_id asc.

---

## 8) Safety checklist for parsers

- [ ] Enforce timeouts on fetch.
- [ ] Enforce max response size.
- [ ] Validate content-type where possible.
- [ ] Do not follow redirects to untrusted hosts.
- [ ] Do not execute scripts or evaluate HTML.
- [ ] Never log full HTML/text bodies.
