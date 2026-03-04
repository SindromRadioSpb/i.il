# .agents/skills/news-pipeline/SKILL.md — Ingestion, Dedupe, Clustering Pack

## Purpose
Implement a reliable news pipeline:
- ingest sources deterministically
- normalize URLs and dedupe safely
- cluster items into stories
- generate summaries cheaply and consistently
- record run history and errors

## Golden rules
- Idempotency is enforced at DB level (unique keys) and in code.
- Never publish full source text; summary-only with attribution.
- One source failure must not break the run.

---

## Pre-patch checklist (run before writing code)

```bash
bash scripts/verify_repo.sh   # all required files present
bash scripts/verify_env.sh    # local env vars set
bash scripts/ci.sh            # current state is green
```

If any check fails, fix it first before writing new code.

---

## Risk matrix

| Risk | Trigger | Mitigation |
|------|---------|------------|
| **SSRF** | User-controlled URLs in source registry | Validate scheme (http/https only); block private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x, ::1); never follow redirects to private ranges |
| **Duplicate stories** | Re-run with same items | Enforce `UNIQUE(item_key)` in DB; use INSERT OR IGNORE; test with dedupe re-run fixture |
| **API regression** | Changing router.ts response shape | Check `docs/API_CONTRACT.md` before any shape change; update contract + tests together |
| **Translation cost runaway** | Unbounded item processing | Enforce `MAX_NEW_ITEMS_PER_RUN` hard cap; memoize by `summary_hash` |
| **Cron overrun** | Run takes > 60s | Cap source count per run; use `MAX_NEW_ITEMS_PER_RUN`; log `duration_ms` |
| **FB double-post** | Re-run with posted stories | Check `fb_status='posted'` + `fb_post_id` before posting; use DB state as single source of truth |
| **Paywall false-positive** | Empty content mistaken for paywall | Use `date_confidence` and `snippet_he` length to classify; do not skip based on empty body alone |
| **Log leakage** | Logging raw content | Never log: `snippet_he` > 100 chars, full HTML, tokens, credentials |

---

## Patch recipe (patch steps / tests / DoD)

### Patch steps
1) Ingest phase:
   - load enabled sources from registry
   - fetch with throttle and backoff
   - validate URL scheme before fetch (SSRF guard)
   - parse entries deterministically (sorted)
2) Normalize + dedupe:
   - normalize URL (lowercase scheme+host, strip tracking params)
   - compute `item_key` = `sha256(normalized_url)`
   - upsert by unique key (INSERT OR IGNORE or ON CONFLICT DO NOTHING)
3) Cluster:
   - compute title tokens
   - find candidate stories within time window
   - match via Jaccard threshold and separators
   - attach item, update story timestamps
4) Summaries:
   - choose small inputs (title + short snippet ≤ 500 chars)
   - apply glossary
   - enforce format sections
   - apply numeric guard (preserve numbers exactly)
   - memoize by hash (skip regeneration if inputs unchanged)
5) Publish state:
   - mark story published to web
   - optional crosspost state updated separately
6) Record run:
   - counters + errors per source/phase

### Tests required for each patch
- URL normalization and hashing tests (deterministic output)
- Ingest integration test with mocked fetch fixtures (fixture files in `apps/worker/test/fixtures/`)
- Dedupe re-run test: same items ingested twice → count unchanged
- Clustering match/no-match tests with title pairs
- Summary format and numeric guard tests
- SSRF guard test: private IP URLs rejected

### Fixtures protocol
- One fixture file per source type: `apps/worker/test/fixtures/{source_id}.{rss|html|json}`
- Fixture must be a real captured response (redact any personal data)
- Fixture filename must match source `id` in `sources/registry.yaml`
- Add fixture before enabling any new source
- Keep fixtures minimal (≤ 5 items); do not store full feed dumps

### DoD
- [ ] Items are deduped by `item_key`
- [ ] Stories cluster duplicates and avoid spam
- [ ] Summaries are compliant (summary-only, attributed) and stable (memoized)
- [ ] Run history written every time (success + partial_failure + failure)
- [ ] Errors captured per source without aborting whole run
- [ ] SSRF guard in place for fetch operations
- [ ] `bash scripts/ci.sh` passes (lint + typecheck + test)
- [ ] `docs/API_CONTRACT.md` and `docs/DB_SCHEMA.md` up to date if behavior changed

---

## Post-patch checklist

```bash
bash scripts/ci.sh     # green
```

Then update `docs/CHANGELOG.md` with the patch entry.

---

## Anti-patterns
- Per-item DB queries inside loops (N+1)
- Publishing content without attribution
- Refreshing summaries on every minor update without memoization
- Unbounded ingestion (no caps) causing cron overruns
- Fetching URLs without SSRF validation
- Logging full article content, tokens, or credentials
- Changing API response shapes without updating `docs/API_CONTRACT.md`
