# docs/AUTONOMY_CHECKLIST.md — Autonomous Setup & Operation Checklist

This document answers three questions:
1. **What does the user (human) need to provide?**
2. **What does the agent do autonomously?**
3. **Where is human decision required, even in autonomous mode?**

Use this before starting any autonomous build session, and after every environment reset.

---

## 1) What the user must provide

### 1.1 Accounts & access (one-time setup)

| Item | Required for | How to provide |
|------|-------------|----------------|
| **Cloudflare account** | Workers + Pages + D1 | Sign up at dash.cloudflare.com |
| `wrangler login` completed | All wrangler commands | Run `pnpm -C apps/worker wrangler login` |
| **D1 database created** | DB operations | `wrangler d1 create news_hub_dev` → note `database_id` |
| `database_id` in `wrangler.toml` | DB binding | Edit `apps/worker/wrangler.toml` |
| **Facebook Page** | FB crossposting (optional) | Existing Page required |
| **Facebook App** with Pages API permission | FB crossposting (optional) | apps.facebook.com |
| **Facebook Page Access Token** | FB crossposting (optional) | Via FB Graph Explorer or App dashboard |

### 1.2 Cloudflare Secrets (production / staging)

These must be provided via `wrangler secret put`, never committed to repo.

| Secret name | Required | Purpose |
|-------------|----------|---------|
| `FACEBOOK_PAGE_ACCESS_TOKEN` | For FB crossposting | Post to Page via Graph API |
| `ADMIN_SHARED_SECRET` | If admin endpoints enabled | Gate admin API |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | If Google Translate used | Cloud Translate auth |
| `DEEPL_API_KEY` | If DeepL used instead | Alternative translation provider |

**Commands:**
```bash
# Run from apps/worker directory:
pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN
pnpm -C apps/worker wrangler secret put ADMIN_SHARED_SECRET
pnpm -C apps/worker wrangler secret put GOOGLE_APPLICATION_CREDENTIALS_JSON
```

### 1.3 Non-secret configuration (in wrangler.toml or env)

| Variable | Default | Must change? |
|----------|---------|-------------|
| `FACEBOOK_PAGE_ID` | (empty) | Yes, for FB posting |
| `FACEBOOK_APP_ID` | (empty) | Yes, for FB posting |
| `TRANSLATION_PROVIDER` | `google` | Set to `none` to disable, or `deepl` |
| `GOOGLE_CLOUD_PROJECT_ID` | (empty) | Yes, if using Google Translate |
| `CRON_ENABLED` | `false` | Set to `true` in production |
| `FB_POSTING_ENABLED` | `false` | Set to `true` when ready |
| `ADMIN_ENABLED` | `false` | Keep `false` in prod; `true` in dev only |

### 1.4 Domain & DNS

| Item | Required for | Notes |
|------|-------------|-------|
| Custom domain for Worker | Production API | Cloudflare DNS or custom domain in dashboard |
| Custom domain for Pages | Production web | Cloudflare Pages → Custom domains |
| `PUBLIC_API_BASE_URL` | Web frontend | Set to production Worker URL |
| `PUBLIC_SITE_BASE_URL` | Canonical links | Set to production Pages URL |

### 1.5 Sources registry

- Review and enable sources in `sources/registry.yaml`
- `enabled: true` starts ingestion on next Cron run
- Add fixtures for any new source type before enabling

### 1.6 D1 Migrations

The user must explicitly apply migrations to remote DB:
```bash
# Apply to dev (remote):
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --file ../../db/migrations/001_init.sql

# Verify:
pnpm -C apps/worker wrangler d1 execute news_hub_dev --remote \
  --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
```

---

## 2) What the agent does autonomously

### 2.1 Development & quality

| Action | When |
|--------|------|
| Run `bash scripts/ci.sh` | After every patch |
| Run `bash scripts/verify_repo.sh` | Before starting work |
| Run `bash scripts/verify_env.sh` | When checking local dev readiness |
| Write/update tests for any changed logic | Per QUALITY_GATES.md |
| Update docs (SPEC/API_CONTRACT/DB_SCHEMA) | When behavior changes |
| Add entries to CHANGELOG.md | After each patch |
| Commit with conventional commit messages | After passing CI gate |

### 2.2 Local D1 operations (safe)

- `wrangler dev --local` — uses local SQLite, safe to run anytime
- SQL via `wrangler d1 execute --local` — local only, safe
- Schema validation tests against migration SQL

### 2.3 Documentation

- Create/update any file in `docs/`
- Update `AGENTS.md`, `README.md`, `scripts/`
- Update `sources/registry.yaml` for source changes (but not enable/disable without user confirmation)

### 2.4 Testing

- Run `pnpm -C apps/worker test` and `pnpm -C apps/web test`
- Add test fixtures under `apps/worker/test/fixtures/`
- Run typecheck and lint for both apps

---

## 3) Boundaries of autonomy (human decision required)

### 3.1 NEVER autonomous (hard rules)

| Action | Why |
|--------|-----|
| `wrangler deploy` | Modifies production |
| `wrangler d1 migrations apply --remote` | Changes prod/staging DB |
| `wrangler secret put` | Secrets management |
| Posting to Facebook Page | External real-world action |
| Enabling/disabling sources in `registry.yaml` | Editorial decision |
| Changing `CRON_ENABLED=true` in prod | Starts real automation |
| Rotating tokens | Security action |

### 3.2 Requires explicit user approval

| Action | Trigger |
|--------|---------|
| Changing API response shape | Would break web frontend |
| Adding new env var as **required** | Affects deployment checklist |
| New D1 migration | Schema change — user decides when to apply remote |
| Disabling a source permanently | Editorial decision |
| Changing cron schedule | Infrastructure change |
| Changing `risk_level` logic | Compliance decision |

### 3.3 Agent self-checks before any patch

Before writing code or docs, agent must verify:

```bash
bash scripts/verify_repo.sh    # all required files present
bash scripts/verify_env.sh     # local dev env vars set (for coding session)
bash scripts/ci.sh             # current state is green
```

If any check fails, fix it first (PATCH-00 prerequisites).

---

## 4) Facebook setup guide (for user)

### Step 1: Create a Facebook App
1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create app → type: "Business" or "Other"
3. Add product: **Pages API**
4. Required permission: `pages_manage_posts`

### Step 2: Get a Page Access Token
1. In Graph API Explorer: select your App + Page
2. Generate token with `pages_manage_posts` permission
3. Exchange for a long-lived token (valid for ~60 days)
4. Store via: `pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN`

### Step 3: Set Page ID
1. Find your Page ID in Page Settings → About
2. Add to `wrangler.toml` under `[vars]`:
   ```toml
   FACEBOOK_PAGE_ID = "your_page_id_here"
   ```

### Step 4: Enable posting
```toml
# apps/worker/wrangler.toml
[vars]
FB_POSTING_ENABLED = "true"
```

> **Security:** Never commit the actual token. Only commit the variable name.
> Long-lived tokens expire. Set a calendar reminder to rotate 2 weeks before expiry.

---

## 5) Google Cloud Translate setup (optional)

### Step 1: Create project and enable API
```bash
gcloud projects create news-hub-translate
gcloud services enable translate.googleapis.com --project=news-hub-translate
```

### Step 2: Create service account
```bash
gcloud iam service-accounts create news-hub-translator \
  --project=news-hub-translate
gcloud projects add-iam-policy-binding news-hub-translate \
  --member="serviceAccount:news-hub-translator@news-hub-translate.iam.gserviceaccount.com" \
  --role="roles/cloudtranslate.user"
gcloud iam service-accounts keys create key.json \
  --iam-account=news-hub-translator@news-hub-translate.iam.gserviceaccount.com
```

### Step 3: Store as Cloudflare secret
```bash
# Paste the contents of key.json when prompted:
pnpm -C apps/worker wrangler secret put GOOGLE_APPLICATION_CREDENTIALS_JSON
# Delete local key file:
rm key.json
```

---

## 6) Pre-launch checklist (production readiness)

- [ ] `wrangler login` completed
- [ ] D1 database created and `database_id` in `wrangler.toml`
- [ ] All migrations applied to remote DB
- [ ] All required secrets set via `wrangler secret put`
- [ ] `FACEBOOK_PAGE_ID` and `FACEBOOK_APP_ID` in `wrangler.toml` vars
- [ ] `PUBLIC_API_BASE_URL` points to production Worker URL
- [ ] `PUBLIC_SITE_BASE_URL` points to production Pages URL
- [ ] At least one source enabled in `sources/registry.yaml` with fixture
- [ ] `bash scripts/ci.sh` passes
- [ ] `GET /api/v1/health` returns `200 ok`
- [ ] Test Cron manually: `POST /api/v1/admin/cron/run` (requires `ADMIN_ENABLED=true` + secret)
- [ ] Verify no stories duplicate on re-run
- [ ] Enable `CRON_ENABLED=true` only after manual test confirms idempotency
