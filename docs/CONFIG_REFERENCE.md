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
| `PUBLIC_SITE_BASE_URL` | string | `http://localhost:3000` | Prod only | No | Any HTTP(S) URL | Canonical site base URL for OG/SEO links |

**Notes:**
- In production, `PUBLIC_API_BASE_URL` must point to the deployed Worker URL (e.g., `https://news-hub.your-domain.workers.dev`).
- `PUBLIC_SITE_BASE_URL` is used to generate canonical `<link>` tags and OG `url` properties.

---

## 2) Worker — feature flags

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `CRON_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Enables cron ingestion logic. Keep `false` in dev unless testing cron. |
| `FB_POSTING_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Enables Facebook crossposting. Enable only after full manual test. |
| `ADMIN_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Enables admin endpoints (dev only; **must be `false` in prod**). |

**Boolean-string convention:** Workers can only store string vars. Code reads `env.VAR === 'true'`.

---

## 3) Worker — translation

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `TRANSLATION_PROVIDER` | string | `"google"` | Yes | No | `"google"` \| `"deepl"` \| `"none"` | Which translation backend to use. `"none"` disables translation. |
| `GOOGLE_CLOUD_PROJECT_ID` | string | `""` | If provider=google | No | GCP project ID | Google Cloud project for Translate API |
| `GOOGLE_CLOUD_LOCATION` | string | `"global"` | If provider=google | No | `"global"` or region | Google Cloud Translate location |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | JSON string | — | If provider=google | **YES** | Service account key JSON | GCP service account credentials. Set via `wrangler secret put`. |
| `DEEPL_API_KEY` | string | — | If provider=deepl | **YES** | DeepL API key | DeepL API authentication. Set via `wrangler secret put`. |

**Security:** `GOOGLE_APPLICATION_CREDENTIALS_JSON` contains a full service account key — treat as highest-sensitivity secret. Never log, never commit.

---

## 4) Worker — Facebook crossposting

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `FACEBOOK_PAGE_ID` | string | `""` | If FB enabled | No | Numeric string | Facebook Page numeric ID (from Page Settings → About) |
| `FACEBOOK_APP_ID` | string | `""` | Optional | No | Numeric string | Facebook App ID (for metadata; not strictly required for posting) |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | string | — | If FB enabled | **YES** | Page access token | Long-lived Page access token. Set via `wrangler secret put`. Expires ~60 days. |

**Rotation reminder:** Long-lived tokens expire. Calendar reminder: rotate 2 weeks before expiry.

---

## 5) Worker — admin & security

| Variable | Type | Default | Required | Secret | Valid values | Purpose |
|----------|------|---------|----------|--------|--------------|---------|
| `ADMIN_ENABLED` | boolean-string | `"false"` | Yes | No | `"true"` \| `"false"` | Guard for admin endpoints. Prod value: `false`. |
| `ADMIN_SHARED_SECRET` | string | — | If admin enabled | **YES** | Any strong random string | Header value for `X-Admin-Secret`. Set via `wrangler secret put`. |

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

---

## 8) Environment matrix

| Variable | Local dev | Staging | Production |
|----------|-----------|---------|------------|
| `CRON_ENABLED` | `false` | `false` (test manually) | `true` (only after manual test) |
| `FB_POSTING_ENABLED` | `false` | `false` | `true` (only after idempotency verified) |
| `ADMIN_ENABLED` | `true` | `true` | **`false`** |
| `TRANSLATION_PROVIDER` | `none` (or `google`) | `google` | `google` |
| `PUBLIC_API_BASE_URL` | `http://127.0.0.1:8787` | staging URL | production URL |

---

## 9) Setting secrets (commands)

```bash
# Run from project root:
pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN
pnpm -C apps/worker wrangler secret put ADMIN_SHARED_SECRET
pnpm -C apps/worker wrangler secret put GOOGLE_APPLICATION_CREDENTIALS_JSON
pnpm -C apps/worker wrangler secret put DEEPL_API_KEY
```

List currently set secrets:
```bash
pnpm -C apps/worker wrangler secret list
```

Delete a secret:
```bash
pnpm -C apps/worker wrangler secret delete SECRET_NAME
```

---

## 10) Validation notes

- **Boolean-string**: always compare `=== 'true'`; any other value (empty string, `'1'`, `'yes'`) is `false`.
- **Integer-string**: always parse with `parseInt(val, 10)`; validate range with guard (e.g., `isNaN` check + clamp).
- **Empty string default**: vars with default `""` are optional at runtime but must exist in the `wrangler.toml [vars]` table for type safety.
- **Secrets not in wrangler.toml**: secrets must NOT appear in `[vars]`; they are injected by Cloudflare at runtime.
