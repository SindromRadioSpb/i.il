# docs/OBSERVABILITY.md — Logging, Metrics, SLOs (A1)

This document defines how we observe the system:
logs, run history, counters, and operational signals.

Goal: enable fast diagnosis, prove reliability for portfolio-grade quality, and avoid secrets/PII leakage.

---

## 1) Principles

- **Structured logs**: machine-parseable, consistent keys.
- **Correlation**: every log line connects to a `run_id` and, when applicable, `source_id`, `item_id`, `story_id`.
- **No secrets**: never log tokens or credential payloads.
- **No full bodies**: do not log full article text; allow safe truncated snippets only when necessary.
- **Persistent run history** in D1: run summaries and error events survive log retention limits.

---

## 2) Logging standard

### 2.1 Required fields
Every log line should include at least:
- `ts` (ISO)
- `level` (info|warn|error)
- `msg` (short)
- `run_id` (nullable for non-cron endpoints)
- `phase` (fetch|parse|dedupe|cluster|summary|publish_web|publish_fb|api|...)
- `duration_ms` (when applicable)

When applicable:
- `source_id`
- `item_id`
- `story_id`
- `http_status`
- `attempt` (retry count)
- `err_code`, `err_msg` (truncated)

### 2.2 Example logs
```json
{"ts":"2026-02-27T08:00:00Z","level":"info","msg":"cron start","run_id":"01J...","phase":"cron","duration_ms":0}
```

```json
{"ts":"...","level":"warn","msg":"source fetch failed","run_id":"01J...","phase":"fetch","source_id":"ynet","http_status":503,"attempt":2,"err_msg":"upstream unavailable"}
```

### 2.3 Redaction
If you must reference a token for debugging:
- log only `token_prefix` and `token_suffix`
- never log full headers, cookies, or credential JSON

---

## 3) Persistent run history (D1)

### 3.1 Run record (required)
Each Cron run creates a `Run` row with:
- `run_id`
- `started_at`, `finished_at`
- `status`: `success|partial_failure|failure`
- counters:
  - `sources_ok`, `sources_failed`
  - `items_found`, `items_new`
  - `stories_new`, `stories_updated`
  - `published_web`, `published_fb`
  - `errors_total`
- `error_summary` (short)

### 3.2 ErrorEvent records
For each notable error:
- `run_id`
- `phase`
- `source_id` (nullable)
- `story_id` (nullable)
- `code` (http/internal)
- `message` (truncated)
- `created_at`

### 3.3 Run lock visibility
Track lock acquisition failures:
- `lock_name`
- `lease_owner`
- `lease_until`
- log a warning if lock is held too long

---

## 4) Metrics (derived from run history)

We treat D1 run history as the canonical metrics source.

### 4.1 Core counters (per run)
- `items_new`
- `stories_new`
- `stories_updated`
- `published_fb`
- `sources_failed`
- `errors_total`
- `duration_ms_total`

### 4.2 Daily aggregates
- total stories published
- coverage per category
- average time from item first seen → story published (latency)
- % runs with partial failures
- top failing sources and phases

---

## 5) SLOs (service level objectives)

For scenario A (50 news/day) we target:

### 5.1 Freshness SLO
- **Breaking freshness:** 80% of breaking stories published within **15 minutes** of first item seen.
- **Regular freshness:** 90% of stories published within **2 hours**.

### 5.2 Reliability SLO
- 99% of Cron runs complete (success or partial_failure) without crashing.
- < 1% runs in `failure` over a rolling 7-day window.

### 5.3 Crosspost SLO
- 95% of eligible stories crossposted to FB successfully within 30 minutes.
- Authentication errors trigger automatic pause of FB attempts until resolved.

---

## 6) Alerting rules (practical)

Even without a full alerting stack, we can create “alert conditions” based on run history:

### 6.1 Critical
- Consecutive `failure` runs ≥ 2
- Lock stuck (lease_age > 2× cron interval)
- FB auth errors detected (401/403)

### 6.2 Warning
- source failure rate > 30% in last 24h
- average run duration > 30s (scenario A)
- spike: items_found > 3× baseline

---

## 7) Dashboards (minimal but impressive)

For portfolio-grade demonstration, implement at least one:
- `/api/health` returning last run status + counters (no secrets)
- “Ops page” in web (optional) showing:
  - last 20 runs (duration, status, counters)
  - top failing sources
  - average freshness

**Important:** the ops page must be non-sensitive and may be gated or disabled in prod if desired.

---

## 8) What not to log

- Full article bodies
- Facebook tokens, Graph API headers
- Translation provider credentials
- Personal data (PII)
- Raw HTML content (unless sanitized and explicitly allowed)

---

## 9) Verification checklist

- [ ] Logs include required fields and are consistent across phases.
- [ ] Run history records are written for every Cron run.
- [ ] Error events are recorded and searchable by run/source/phase.
- [ ] No secrets appear in logs (spot-check).
- [ ] `/api/health` returns safe operational summary.
