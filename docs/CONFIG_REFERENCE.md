# docs/CONFIG_REFERENCE.md — Configuration Reference

Complete reference for all environment variables and configuration values.

- **Worker vars** are set in `apps/worker/wrangler.toml` (`[vars]`) for non-secret config,
  and via `wrangler secret put` for secrets.
- **Web vars** are set in `.env` (dev) or the Cloudflare Pages environment dashboard (prod).
- **Secrets** must NEVER be committed to the repo.

Local dev can use `.env` (copy from `.env.example`). For Workers, Wrangler picks up vars from
`wrangler.toml`; secrets from `wrangler secret put` only.

---

## 1) Web app (`apps/web`)

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `PUBLIC_API_BASE_URL` | string | `http://127.0.0.1:8787` | Yes | No | Any HTTP(S) URL | Worker API base URL used by the web frontend |
| `PUBLIC_SITE_BASE_URL` | string | `http://localhost:4321` | Prod only | No | Any HTTP(S) URL | Canonical site base URL for OG/SEO links |
| `PUBLIC_ADMIN_TOKEN` | string | `""` | If ops page used | No* | Random hex string | Passed as `x-admin-token` header from ops.astro to Worker admin endpoints. Set in Cloudflare Pages environment dashboard. |

**Notes:**
- In production, `PUBLIC_API_BASE_URL` must point to the deployed Worker URL (e.g., `https://iil.sindromradiospb.workers.dev`).
- `PUBLIC_SITE_BASE_URL` is used to generate canonical `<link>` tags and OG `url` properties. Current prod value: `https://iil-web.pages.dev`.
- `PUBLIC_ADMIN_TOKEN` is technically non-secret at the Astro/CDN layer (it's a public env var), but should still be treated as sensitive: set it in the Pages dashboard, not in committed files.

---

## 2) Worker — feature flags

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `CRON_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Enables cron ingestion logic. Keep `false` in dev unless testing cron. |
| `FB_POSTING_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Enables Facebook crossposting. Enable only after full manual test. |
| `ADMIN_ENABLED` | boolean-string | `"true"` | Yes | No | `"true"` \| `"false"` | Enables admin endpoints. Can be `true` in prod when `ADMIN_SECRET_TOKEN` is set. |

**Boolean-string convention:** Workers can only store string vars. Code reads `env.VAR === 'true'`.

---

## 3) Worker — AI / summary providers

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `SUMMARY_PROVIDERS` | comma-list | `"gemini,claude,google_translate,rule_based"` | Yes | No | Provider IDs | Ordered provider chain for summary generation. First healthy provider wins. |
| `ANTHROPIC_MODEL` | string | `"claude-haiku-4-5-20251001"` | If claude in chain | No | Model ID string | Anthropic model ID used for summary generation |
| `GEMINI_MODEL` | string | `"gemini-2.0-flash"` | If gemini in chain | No | Model ID string | Google Gemini model ID |
| `ANTHROPIC_API_KEY` | string | — | If claude in chain | **YES** | API key | Anthropic API key. Set via `wrangler secret put ANTHROPIC_API_KEY`. |
| `GEMINI_API_KEY` | string | — | If gemini in chain | **YES** | API key | Google Gemini API key. Set via `wrangler secret put GEMINI_API_KEY`. |

---

## 4) Worker — Facebook crossposting

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `FB_PAGE_ID` | string | `""` | If FB enabled | No | Numeric string | Facebook Page numeric ID (e.g., `1026029350589884`) |
| `FB_PAGE_TOKEN` | string | — | If FB enabled | **YES** | Page Access Token | Long-lived Page Access Token (never User token). Set via `wrangler secret put FB_PAGE_TOKEN`. Never expires if obtained correctly. |

**How to obtain a long-lived Page Access Token:**
1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Request `pages_manage_posts` + `pages_read_engagement` permissions
3. Exchange User token → Page token via `GET /me/accounts`
4. Verify type: `GET /debug_token?input_token=<token>` → `type` must be `PAGE` and `expires_at` must be `0` (non-expiring)

**Rotation:** Non-expiring Page tokens do not need rotation unless revoked. If `fb_status=auth_error` appears in runs, the token has been revoked — obtain a new one and run `wrangler secret put FB_PAGE_TOKEN --env production`.

**Legacy alias:** Code also checks `FB_PAGE_ACCESS_TOKEN` as a fallback. Canonical name is `FB_PAGE_TOKEN`.

---

## 5) Worker — admin & security

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `ADMIN_ENABLED` | boolean-string | `"true"` | Yes | No | `"true"` \| `"false"` | Guard for admin endpoints. Safe to set `true` in prod when `ADMIN_SECRET_TOKEN` is configured. |
| `ADMIN_SECRET_TOKEN` | string | — | Recommended in prod | **YES** | Any strong random string (≥ 32 hex chars) | Required value for `x-admin-token` request header. If not set, admin endpoints have no token check. Set via `wrangler secret put ADMIN_SECRET_TOKEN`. |

**Generate a token:**
```bash
openssl rand -hex 32
```

**Token flow:** Web ops page (`/ops`) sends `x-admin-token: <PUBLIC_ADMIN_TOKEN>`. Worker checks this against `ADMIN_SECRET_TOKEN`. Both values must match.

---

## 6) Worker — tuning parameters

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `CRON_INTERVAL_MIN` | integer-string | `"10"` | Yes | No | `"1"` – `"60"` | Expected cron interval in minutes; used for lock TTL calculations |
| `MAX_NEW_ITEMS_PER_RUN` | integer-string | `"25"` | Yes | No | `"1"` – `"200"` | Hard cap on new items processed per cron run (cost + time guard) |
| `SUMMARY_TARGET_MIN` | integer-string | `"400"` | Yes | No | `"100"` – `"600"` | Minimum Russian summary length in characters |
| `SUMMARY_TARGET_MAX` | integer-string | `"700"` | Yes | No | `"400"` – `"1000"` | Maximum Russian summary length in characters |

**Integer-string convention:** Workers store strings; code parses with `parseInt(env.VAR, 10)`.

---

## 7) D1 database binding

| Binding | Type | wrangler.toml key | Purpose |
|---------|------|-------------------|---------|
| `DB` | D1Database | `[[d1_databases]]` binding `"DB"` | Primary relational database for all Worker data |

The `database_id` in `wrangler.toml` points to the Cloudflare D1 instance. For local dev, Wrangler creates a local SQLite DB automatically (`--local`).

| Environment | Database name | Database ID |
|-------------|---------------|-------------|
| dev | `news_hub_dev` | `3e74b9fd-b0b3-4022-ac3d-d08306015420` |
| production | `news_hub_prod` | `32403483-6512-4673-aaff-a3a6e3c9aad3` |

---

## 8) Environment matrix

| Variable | Local dev | Production |
|----------|-----------|------------|
| `CRON_ENABLED` | `false` | `true` |
| `FB_POSTING_ENABLED` | `false` | `true` |
| `ADMIN_ENABLED` | `true` | `true` (with token) |
| `ADMIN_SECRET_TOKEN` | — | set via `wrangler secret put` |
| `SUMMARY_PROVIDERS` | `"gemini,claude,google_translate,rule_based"` | same |
| `PUBLIC_API_BASE_URL` | `http://127.0.0.1:8787` | `https://iil.sindromradiospb.workers.dev` |
| `PUBLIC_SITE_BASE_URL` | `http://localhost:4321` | `https://iil-web.pages.dev` |
| `PUBLIC_ADMIN_TOKEN` | — | set in Cloudflare Pages dashboard |

---

## 9) Setting secrets (commands)

```bash
# Worker secrets (run from project root):
npx wrangler secret put FB_PAGE_TOKEN --env production
npx wrangler secret put ADMIN_SECRET_TOKEN --env production
npx wrangler secret put ANTHROPIC_API_KEY --env production
npx wrangler secret put GEMINI_API_KEY --env production

# List currently set secrets:
npx wrangler secret list --env production

# Delete a secret:
npx wrangler secret delete SECRET_NAME --env production
```

**Web secrets** (set in Cloudflare Pages dashboard → Settings → Environment variables):
- `PUBLIC_ADMIN_TOKEN` — set as "Plain text" variable (not secret) under Production environment

---

## 10) Validation notes

- **Boolean-string**: always compare `=== 'true'`; any other value (empty string, `'1'`, `'yes'`) is `false`.
- **Integer-string**: always parse with `parseInt(val, 10)`; validate range with guard (e.g., `isNaN` check + clamp).
- **Empty string default**: vars with default `""` are optional at runtime but must exist in the `wrangler.toml [vars]` table for type safety.
- **Secrets not in wrangler.toml**: secrets must NOT appear in `[vars]`; they are injected by Cloudflare at runtime.
- **`Env` interface**: `apps/worker/src/index.ts` defines the TypeScript `Env` interface. Any new var or secret must be added there AND in `wrangler.toml [vars]` (or documented as a secret only).
