# .agents/skills/ops-admin/SKILL.md — Ops & Admin Pack

## Purpose
Operate, monitor, and debug the news hub in production using the ops dashboard and admin API.

---

## Ops page

URL: `<PUBLIC_SITE_BASE_URL>/ops` (e.g., `https://iil-web.pages.dev/ops`)

The ops page shows:
- Service health and last run status
- Top failing sources in the last 24h
- Last 20 cron runs with drill-down error details (click any row)
- Draft stories panel with Hold/Release buttons
- Summary stat cards: total drafts, pending, on hold

Auth: ops page sends `x-admin-token: <PUBLIC_ADMIN_TOKEN>` header automatically.

---

## Admin API endpoints (full reference in `docs/API_CONTRACT.md` §3)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/health` | Service health (public, no auth) |
| `GET /api/v1/admin/runs` | Last 20 run records |
| `GET /api/v1/admin/errors?run_id=X` | Error events for a run |
| `GET /api/v1/admin/drafts` | Draft stories + counts |
| `POST /api/v1/admin/story/:id/hold` | Block story from auto-publishing |
| `POST /api/v1/admin/story/:id/release` | Unblock story |
| `POST /api/v1/admin/cron/trigger` | Fire ingest run on-demand (unreliable, dev only) |

All admin endpoints require `x-admin-token: <ADMIN_SECRET_TOKEN>` header.

---

## Editorial review workflow

1. Open `/ops` → "Draft stories" panel
2. Stories with `editorial_hold=0` are **pending** — will be summarized and published in the next cron run
3. Click **Hold** to set `editorial_hold=1` — story is blocked from auto-publishing
4. Review the story's content in D1 (see `items` table via `title_sample`)
5. Click **Release** to unblock — story resumes in pipeline on next run

**Impact of hold:**
- `getStoriesNeedingSummary` skips held stories (`AND editorial_hold = 0`)
- Summary pipeline does not run for held stories
- Story stays in `state='draft'` until released

---

## Diagnosing run failures

### Check recent runs
```bash
curl -H "x-admin-token: $TOKEN" https://iil.sindromradiospb.workers.dev/api/v1/admin/runs | jq '.data.runs[:3]'
```

### Get errors for a run
```bash
curl -H "x-admin-token: $TOKEN" "https://iil.sindromradiospb.workers.dev/api/v1/admin/errors?run_id=<RUN_ID>" | jq '.data.errors'
```

### Common run statuses
- `success` — all sources fetched, stories published
- `partial_failure` — some sources failed OR some FB posts failed; check error details
- `failure` — catastrophic failure (DB unreachable, lock issue, budget exhausted)
- `in_progress` (stuck) — orphaned run; see cloudflare-wrangler-d1 skill for cleanup SQL

---

## Monitoring checklist (run weekly)

- [ ] Check `/api/v1/health` → `last_run.status` not `failure`
- [ ] Check `top_failing_sources` — if a source is always failing, disable it in `sources/registry.yaml`
- [ ] Check `published_fb` counter > 0 in recent runs (FB posting working)
- [ ] Check ops page draft count — if > 100 drafts accumulating, investigate summary pipeline

---

## Secrets rotation

### ADMIN_SECRET_TOKEN
```bash
openssl rand -hex 32  # generate new token
npx wrangler secret put ADMIN_SECRET_TOKEN --env production
# Then update PUBLIC_ADMIN_TOKEN in Cloudflare Pages dashboard to match
```

### FB_PAGE_TOKEN
1. Get new Page Access Token from Graph Explorer → `GET /me/accounts`
2. Verify: `type=PAGE`, `expires_at=0`
3. `npx wrangler secret put FB_PAGE_TOKEN --env production`

---

## Anti-patterns
- Using `POST /api/v1/admin/cron/trigger` to "test production" — it creates orphaned runs
- Setting `ADMIN_ENABLED=false` in prod without removing `PUBLIC_ADMIN_TOKEN` from Pages (ops page breaks silently)
- Using browser devtools to extract the admin token from ops page HTML (it's a public env var by design — the ADMIN_SECRET_TOKEN on the worker side is the real guard)
