# .agents/skills/facebook-publisher/SKILL.md — Facebook Crossposting Pack

## Purpose
Provide safe, idempotent posting to our **own** Facebook Page using the official Graph API.

## Non-negotiables
- No Facebook scraping.
- Only post via official Pages/Graph API.
- Store `fb_post_id` and status to prevent duplicates.
- Do not log tokens or full request headers.

---

## Environment variables (actual names)

| Var | Where set | Notes |
|-----|-----------|-------|
| `FB_PAGE_ID` | `wrangler.toml [vars]` | Page numeric ID (e.g., `1026029350589884`) |
| `FB_PAGE_TOKEN` | `wrangler secret put FB_PAGE_TOKEN --env production` | Long-lived Page Access Token (never User token). `expires_at=0` means non-expiring. |
| `FB_POSTING_ENABLED` | `wrangler.toml [vars]` | `"true"` to enable posting |

Code reads: `env.FB_PAGE_TOKEN ?? env.FB_PAGE_ACCESS_TOKEN` (alias fallback).

**How to verify token type:**
```bash
curl "https://graph.facebook.com/debug_token?input_token=<TOKEN>&access_token=<TOKEN>"
# Response must have: "type": "PAGE", "expires_at": 0
```

---

## Patch recipe (patch steps / tests / DoD)

### Patch steps
1) Add config gates:
   - `FB_POSTING_ENABLED`
   - `FB_PAGE_ID` in `wrangler.toml [vars]`
   - `FB_PAGE_TOKEN` via `wrangler secret put`
2) Implement Graph client:
   - timeout + retry wrapper (`fetchWithTimeout` from `src/net/`)
   - map errors (401/403/429)
3) Compose message:
   - RU title
   - 2–4 bullets
   - canonical story URL
   - 1–3 hashtags from category
4) Idempotency:
   - if `publications.fb_status=posted` OR `fb_post_id IS NOT NULL`, skip posting
   - also skip if `fb_attempts >= 5` (lifetime cap)
   - store `fb_post_id`, increment `fb_attempts` on each attempt
5) Retry policy:
   - max **5 lifetime attempts** (checked via `fb_attempts < 5`)
   - on FB error code 190, 102 → `auth_error`, stop further attempts this run
   - on FB error code 4, 32 → `rate_limited`, one retry then stop this run
   - `fb_status IN ('disabled', 'failed')` — both are eligible for retry on next run
6) Error status mapping:
   - `fb_status = 'auth_error'` → FB token revoked/invalid; requires token rotation
   - `fb_status = 'rate_limited'` → API throttle; retry on next scheduled run
   - `fb_status = 'failed'` → other FB error; retry next run (up to 5 total attempts)

### Tests
- Mock API success → stores `fb_post_id`, `fb_status='posted'`
- Second attempt on `fb_status='posted'` → does not call API
- FB error code 190 → sets `auth_error` and stops further calls this run
- FB error code 4 → bounded retry then `rate_limited`
- `fb_attempts >= 5` → story skipped

### DoD
- [ ] One story produces at most one FB post
- [ ] `fb_post_id IS NULL` checked before posting (idempotency)
- [ ] `fb_attempts < 5` lifetime cap enforced in DB query (`getStoriesForFbPosting`)
- [ ] Failures are observable (`fb_status`, `fb_error_last`, `fb_attempts` in `publications`)
- [ ] No secrets in logs or responses
- [ ] `bash scripts/ci.sh` passes

---

## Diagnosing FB posting failures

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `published_fb=0` in all runs | `FB_POSTING_ENABLED` not `"true"` | Check `wrangler.toml [env.production.vars]` |
| `fb_status=auth_error` | Token is User token or revoked | Obtain Page Access Token, `wrangler secret put FB_PAGE_TOKEN` |
| `fb_status=rate_limited` | Hit app/page rate limit | Wait for next run; check Graph API quota |
| `fb_status=failed` (code 200) | Wrong token type (User instead of Page) | See above |
| `published_fb=0`, no errors | `getStoriesForFbPosting` returning 0 rows | Check `publications` rows — may have `fb_attempts >= 5` or `web_status != 'published'` |

---

## Anti-patterns
- Posting without checking `fb_post_id` IS NULL (causes duplicate posts)
- Using User Access Token instead of Page Access Token
- Retrying indefinitely without a `fb_attempts` cap
- Logging token values or raw error responses
- Calling Graph API from inside error handlers (infinite retry loops)
