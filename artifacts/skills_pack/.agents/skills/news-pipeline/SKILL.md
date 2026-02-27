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

## Patch recipe (patch steps / tests / DoD)

### Patch steps
1) Ingest phase:
   - load enabled sources from registry
   - fetch with throttle and backoff
   - parse entries deterministically (sorted)
2) Normalize + dedupe:
   - normalize URL
   - compute `item_key`
   - upsert by unique key
3) Cluster:
   - compute title tokens
   - find candidate stories within time window
   - match via Jaccard threshold and separators
   - attach item, update story timestamps
4) Summaries:
   - choose small inputs (title + short snippet)
   - apply glossary
   - enforce format sections
   - apply numeric guard
   - memoize by hash
5) Publish state:
   - mark story published to web
   - optional crosspost state updated separately
6) Record run:
   - counters + errors per source/phase

### Tests
- URL normalization and hashing tests
- Ingest integration test with mocked fetch fixtures
- Dedupe re-run test (no duplicates)
- Clustering match/no-match tests
- Summary format and numeric guard tests

### DoD
- [ ] Items are deduped by `item_key`
- [ ] Stories cluster duplicates and avoid spam
- [ ] Summaries are compliant and stable
- [ ] Run history written every time
- [ ] Errors captured per source without aborting whole run

---

## Anti-patterns
- Per-item DB queries inside loops (N+1)
- Publishing content without attribution
- Refreshing summaries on every minor update without memoization
- Unbounded ingestion (no caps) causing cron overruns
