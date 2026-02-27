# docs/RUNBOOK.md — Operations & Troubleshooting (A1)

This runbook covers the most common operational issues for:
**Cloudflare Workers Cron + D1 + Pages** news hub with Facebook crossposting.

**Rule:** never run production-impacting commands unless explicitly requested.

---

## 1) Quick diagnosis flow (5 minutes)

1) Check health:
- `GET /api/health`
  - last run status, timestamps, counters (no secrets)

2) Identify the failure phase:
- fetch / parse / dedupe / cluster / summary / publish_fb / db

3) Check recent runs in D1 run history (ops page or DB query):
- last 20 runs, statuses, errors_total

4) Check top failing sources:
- is it a single source outage or systemic failure?

5) Apply the relevant playbook below.

---

## 2) Common incidents & playbooks

### 2.1 Cron runs overlapping / duplicates appearing
**Symptoms**
- duplicate items or duplicate FB posts
- run durations exceed cron interval
- lock errors in logs

**Likely causes**
- missing or broken D1 lease lock
- lock TTL too short or not respected
- long-running run due to source timeouts

**Actions**
1) Verify lock table state:
- ensure `RunLock` exists and lease is valid
2) Increase lock TTL (keep within safe bounds)
3) Enforce per-source and per-run time budgets
4) Ensure FB crosspost idempotency:
- `fb_post_id` stored and checked before posting

**Prevent**
- add regression tests for lock behavior
- enforce max items per run + request timeouts

---

### 2.2 A source is failing (RSS/sitemap/html)
**Symptoms**
- `sources_failed` increases
- ErrorEvent phase = fetch or parse
- 4xx/5xx responses, malformed XML/HTML

**Actions**
1) Confirm if source is temporarily down (5xx/timeout)
2) If persistent:
- lower `max_items_per_run`
- increase `min_interval_sec`
- adjust parser selectors/strategies
3) If source changes format:
- add new fixture
- update parser logic
- add regression tests

**Disable a source**
- set `enabled:false` in `sources/registry.yaml`
- document decision if needed (DECISIONS)

---

### 2.3 D1 “database locked” / query errors
**Symptoms**
- worker logs show D1 query failures
- runs fail early

**Likely causes**
- unbounded loops causing heavy DB load
- missing indexes
- concurrent writes without batching

**Actions**
1) Identify hot queries (phase logs)
2) Batch operations (avoid per-row)
3) Add indexes (migration-driven)
4) Limit work per run (max items)

**Prevent**
- performance sanity tests (duration < 30s scenario A)
- query patterns audited in code review

---

### 2.4 Translation failures
**Symptoms**
- summary generation failing
- provider returns 429/503
- missing credentials errors

**Actions**
1) Confirm provider configuration:
- env vars set
- secrets present
2) If rate-limited (429):
- backoff; reduce translation volume per run
- ensure memoization is working (hash cache)
3) If credentials invalid:
- rotate keys; update secrets
- ensure logs do not expose credentials

**Fallback**
- publish story with “summary pending” state (optional)
- or publish minimal summary based on title/snippet (content_confidence=low)

---

### 2.5 Facebook posting fails (401/403)
**Symptoms**
- FB status becomes `auth_error`
- repeated failures

**Actions**
1) Immediately stop FB attempts for current run and mark auth_error
2) Verify token validity:
- ensure correct Page access token
- ensure required permissions are granted
3) Rotate token:
- update Cloudflare secret
4) Re-enable FB after verification

**Prevent**
- a guard: on 401/403, skip further FB calls until next run
- store last auth error timestamp

---

### 2.6 Facebook posting fails (429 rate limit)
**Symptoms**
- 429 returned from Graph API

**Actions**
1) Backoff and retry once (bounded)
2) If continues:
- mark `rate_limited`
- stop further FB attempts this run
3) Reduce posting frequency:
- post only story-level summaries (already)
- optionally batch/digest mode for heavy days

---

### 2.7 Stories appear but web shows empty / SEO missing
**Symptoms**
- API returns data but pages show blank
- canonical/OG tags missing

**Actions**
1) Check web uses correct `PUBLIC_API_BASE_URL`
2) Validate API response schema (contract tests)
3) Ensure SSR/metadata is populated from API response
4) Fix escaping of meta tags

---

## 3) Operational toggles & safe modes

### 3.1 Disable cron (dev or emergency)
- Set `CRON_ENABLED=false` (env var)
- Deploy and verify that scheduled runs stop (or Cron handler returns early)

### 3.2 Disable Facebook crossposting
- Set `FB_POSTING_ENABLED=false`
- Ensure pipeline still publishes to web normally

### 3.3 Reduce ingestion load
- reduce `max_items_per_run` per source
- increase `min_interval_sec`
- cap total new items per run

---

## 4) Backup & restore (D1)

**Policy:** Keep schema migrations and ability to replay ingestion; backups are still recommended.

### 4.1 Backup strategy (recommended)
- periodic export (manual or scheduled outside this repo)
- keep last 7 days + last 4 weeks (minimum)

### 4.2 Restore strategy
- restore D1 snapshot
- verify schema version matches migrations
- run a “dry-run” ingestion to validate health

---

## 5) Deployment playbook (manual)

### 5.1 Pre-deploy checklist
- lint/typecheck/test are green (worker + web)
- migrations prepared and tested locally
- secrets are present in Cloudflare (no secrets in repo)
- compliance: summary-only, attribution enforced

### 5.2 Apply migrations (remote)
Run only when explicitly requested.
- apply forward-only migrations
- verify schema version
- sanity query for key tables

### 5.3 Deploy Worker
- deploy via Wrangler
- verify `/api/health`

### 5.4 Deploy Pages
- deploy web
- verify feed and story pages
- verify canonical/OG tags

---

## 6) Post-incident actions

After resolving an incident:
- Add or update regression tests
- Add fixtures for source format changes
- Update this runbook with the new case
- Record decisions in `docs/DECISIONS.md` if relevant

---

## 7) Quick reference: error classes

- `fetch_error`: network, 5xx, timeout
- `parse_error`: malformed XML/HTML, selector mismatch
- `db_error`: query, constraint, lock
- `translate_error`: provider unavailable, rate limit
- `fb_auth_error`: 401/403
- `fb_rate_limited`: 429
- `unknown_error`: unexpected

Each error record should include:
- run_id, phase, source_id/story_id, code, message, timestamp
