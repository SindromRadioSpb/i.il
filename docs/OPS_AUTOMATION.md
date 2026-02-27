# docs/OPS_AUTOMATION.md — Operational Automation Guide

This document explains the automated Cron pipeline, safe operation modes, manual triggers, recovery, and how to monitor system health.

See also:
- `docs/RUNBOOK.md` — incident response and deployment
- `docs/OBSERVABILITY.md` — structured logs and correlation IDs
- `docs/AUTONOMY_CHECKLIST.md` — what is safe to run autonomously

---

## 1) Cron schedule

### 1.1 Configured schedule
```toml
# apps/worker/wrangler.toml
[triggers]
crons = ["*/10 * * * *"]
```

Every 10 minutes. This is the default. Changing the schedule requires:
1. Editing `wrangler.toml`
2. Human approval (see `docs/AUTONOMY_CHECKLIST.md §3.2`)
3. Redeployment

### 1.2 What each run does
```
Cron fires
  └─ Acquire run_lock (TTL = CRON_INTERVAL_MIN * 60 + 60 s)
  └─ If lock held → exit (previous run still in progress)
  └─ Start run (insert into `runs`, status=in_progress)
  ├─ For each enabled source:
  │   ├─ Fetch feed (RSS/sitemap/HTML)
  │   ├─ Parse + normalize entries
  │   ├─ Dedupe by item_key (UNIQUE constraint)
  │   ├─ Cluster into stories (Jaccard threshold)
  │   └─ Record source success/error
  ├─ Generate/update summaries (memoized by hash)
  ├─ Publish stories to web (update web_status)
  ├─ [If FB_POSTING_ENABLED] Crosspost to Facebook Page
  └─ Finish run (update `runs` row, release lock)
```

### 1.3 Cron enabled/disabled
- `CRON_ENABLED=false`: the Cron trigger still fires, but the handler exits immediately (no-op).
- `CRON_ENABLED=true`: full pipeline runs.
- **Default is `false`** — must be explicitly enabled in production.

---

## 2) Safe operation modes

### 2.1 Fully safe (dev default)
```toml
CRON_ENABLED = "false"
FB_POSTING_ENABLED = "false"
ADMIN_ENABLED = "false"
```
- No automated runs.
- No Facebook posts.
- No admin endpoints exposed.
- Worker responds to API reads only.

### 2.2 Read-only dev (local test)
```toml
CRON_ENABLED = "false"
FB_POSTING_ENABLED = "false"
ADMIN_ENABLED = "true"   # dev only, never prod
```
- Admin endpoints available for manual triggers.
- No automated runs.
- No Facebook posts.

### 2.3 Cron-only (no FB)
```toml
CRON_ENABLED = "true"
FB_POSTING_ENABLED = "false"
ADMIN_ENABLED = "false"
```
- Cron ingests, clusters, generates summaries, publishes to web.
- No Facebook crossposting.
- Safe to run in staging.

### 2.4 Full production
```toml
CRON_ENABLED = "true"
FB_POSTING_ENABLED = "true"
ADMIN_ENABLED = "false"   # always false in prod
```
- Full pipeline with FB crossposting.
- Only enable after `POST /api/v1/admin/cron/run` manual test confirms idempotency.

---

## 3) Manual trigger (dev)

Requires `ADMIN_ENABLED=true` and `ADMIN_SHARED_SECRET` set.

### 3.1 Trigger a run
```bash
curl -X POST http://127.0.0.1:8787/api/v1/admin/cron/run \
  -H "X-Admin-Secret: <your-admin-secret>"
```

Expected response:
```json
{ "ok": true, "data": { "run_id": "01HZ..." } }
```

### 3.2 Check run result
Poll `GET /api/v1/health` until `last_run.status` changes from `null`:
```bash
curl http://127.0.0.1:8787/api/v1/health | jq '.last_run'
```

### 3.3 Re-run without duplicates
Re-running the same cron manually is safe. The dedupe invariant (`UNIQUE(item_key)`) ensures no duplicate items are inserted. Idempotent upsert logic handles re-runs gracefully.

---

## 4) Reading the health endpoint

```
GET /api/v1/health
```

### 4.1 Full response interpretation

```json
{
  "ok": true,
  "service": {
    "name": "news-hub",
    "version": "0.1.0",
    "env": "dev | prod",
    "now_utc": "2026-02-27T10:00:00.000Z"
  },
  "last_run": {
    "run_id": "01HZ...",
    "started_at": "2026-02-27T09:50:00.000Z",
    "finished_at": "2026-02-27T09:50:14.231Z",
    "status": "success | partial_failure | failure",
    "counters": {
      "sources_ok": 5,
      "sources_failed": 0,
      "items_found": 42,
      "items_new": 7,
      "stories_new": 3,
      "stories_updated": 2,
      "published_web": 3,
      "published_fb": 3,
      "errors_total": 0
    },
    "duration_ms": 14231
  }
}
```

### 4.2 Status interpretation

| `last_run.status` | Meaning |
|-------------------|---------|
| `null` | No run has completed since Worker started (or `CRON_ENABLED=false`) |
| `success` | All sources succeeded, all publications succeeded |
| `partial_failure` | Some sources failed or some publications failed, but run completed |
| `failure` | Run aborted (unhandled error, lock issues, etc.) |

### 4.3 Health check decision tree

```
last_run is null?
  → Yes: Was cron recently enabled? Wait 10 min. Or trigger manually.
  → No:
      status = success: Normal. Monitor duration_ms.
      status = partial_failure:
        Check sources_failed > 0 → source fetch/parse error (see error_events)
        Check errors_total > 0 → DB or translation error
      status = failure:
        Check RUNBOOK.md §3 for recovery steps
```

---

## 5) Run history (D1 queries)

Check last 10 runs:
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT run_id, started_at, status, duration_ms, errors_total FROM runs ORDER BY started_at DESC LIMIT 10;"
```

Check errors for a specific run:
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT phase, source_id, code, message FROM error_events WHERE run_id='RUN_ID_HERE';"
```

Check publication backlog (items pending FB posting):
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT COUNT(*) FROM publications WHERE fb_status='pending';"
```

---

## 6) Lock management

The `run_lock` table prevents overlapping runs.

### 6.1 Check current lock state
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT lock_name, lease_owner, lease_until FROM run_lock;"
```

### 6.2 Stuck lock (recovery)
If a run crashed and the lock was not released:
1. Verify no run is currently in progress (check `runs` table for any `status='in_progress'`)
2. Only then, manually release the lock:
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "DELETE FROM run_lock WHERE lock_name='cron';"
```
3. Record the incident in `docs/DECISIONS.md`

---

## 7) Facebook posting recovery

### 7.1 Failed posts
Stories with `fb_status='failed'` will retry on next run (up to a max attempt count — see code).

Check failed posts:
```bash
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT story_id, fb_status, fb_attempts, fb_error_last FROM publications WHERE fb_status NOT IN ('posted','disabled') ORDER BY story_id DESC LIMIT 20;"
```

### 7.2 Auth error
`fb_status='auth_error'` means the token is expired or invalid.
1. Generate a new long-lived token (see `docs/AUTONOMY_CHECKLIST.md §4`)
2. Update the secret: `pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN`
3. Redeploy the Worker
4. Stories with `auth_error` will retry on next run

### 7.3 Rate limited
`fb_status='rate_limited'` means Facebook returned 429.
- The Worker will back off automatically on the next run.
- No manual intervention needed unless it persists for > 1 hour.

---

## 8) Cost controls

| Control | Default | Effect |
|---------|---------|--------|
| `MAX_NEW_ITEMS_PER_RUN` | 25 | Hard cap on items processed per run; prevents runaway translation costs |
| `TRANSLATION_PROVIDER=none` | — | Disables translation entirely (summaries will be missing) |
| `CRON_ENABLED=false` | default | Stops all automated runs |
| Summary memoization | always-on | Reuses existing translation if `summary_hash` unchanged |

To switch translation off temporarily:
```toml
# apps/worker/wrangler.toml
[vars]
TRANSLATION_PROVIDER = "none"
```
Then redeploy. No data loss — stories will regenerate summaries when provider is re-enabled.

---

## 9) Monitoring checklist

Daily (automated or manual):
- [ ] `GET /api/v1/health` returns 200 and `last_run.status` = `success` or `partial_failure`
- [ ] `duration_ms` < 55000 (must complete within 60s Cron wall time)
- [ ] `errors_total` not growing

Weekly:
- [ ] `sources_failed` count — investigate any persistent source failures
- [ ] `fb_status` counts — ensure no growing `auth_error` or `failed` backlog
- [ ] Review `runs` table for runs with `status=failure`

Monthly:
- [ ] Check Facebook token expiry (rotate 2 weeks before)
- [ ] Check Google Cloud Translate quota usage
- [ ] Review D1 storage usage
