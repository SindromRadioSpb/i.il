# .agents/skills/facebook-publisher/SKILL.md — Facebook Crossposting Pack

## Purpose
Provide safe, idempotent posting to our **own** Facebook Page using the official API.

## Non-negotiables
- No Facebook scraping.
- Only post via official Pages/Graph API.
- Store `fb_post_id` and status to prevent duplicates.
- Do not log tokens or full request headers.

---

## Patch recipe (patch steps / tests / DoD)

### Patch steps
1) Add config gates:
   - `FB_POSTING_ENABLED`
   - `FACEBOOK_PAGE_ID`
   - secret token via Wrangler secret
2) Implement Graph client:
   - timeout + retry wrapper
   - map errors (401/403/429)
3) Compose message:
   - RU title
   - 2–4 bullets
   - canonical story URL
   - 1–3 hashtags from category
4) Idempotency:
   - if `publications.fb_status=posted` or `fb_post_id` exists, skip posting
   - store attempts and last error
5) Retry policy:
   - max 3 attempts per run
   - on 401/403 -> auth_error, stop further attempts this run
   - on 429 -> one retry with backoff, then rate_limited

### Tests
- Mock API success -> stores fb_post_id
- Second attempt does not repost
- 401/403 -> auth_error and no further calls
- 429 -> bounded retry and recorded failure

### DoD
- [ ] One story produces at most one FB post
- [ ] Failures are observable and retry-safe
- [ ] No secrets in logs or responses

---

## Anti-patterns
- Posting without checking publication state
- Retrying infinitely
- Logging token values
