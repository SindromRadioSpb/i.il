# docs/SECURITY.md — Security Policy (A1: Cloudflare Pages + Workers + D1)

This document defines non-negotiable security rules for this project.

If a requirement conflicts with this document, **this document wins**.

---

## 1) Threat model (practical)

We assume:
- Attackers can read public repository content.
- Logs might be aggregated/forwarded; accidental leakage is a primary risk.
- Source sites and third-party APIs can be unreliable or malicious (HTML injection, unexpected payloads).
- Overlapping Cron runs can corrupt state or create duplicates if locks are missing.
- Credential compromise (FB tokens, translation keys) leads to account damage and reputational harm.

Primary risks:
- **Secrets exposure** (repo, logs, client-side)
- **Unauthorized posting** (Facebook token misuse)
- **Data corruption** (D1, concurrency bugs)
- **SSRF/unsafe fetch** (worker fetching untrusted URLs)
- **Supply chain** (dependency compromises)

---

## 2) Secrets & credentials

### 2.1 Never commit secrets
Do not commit:
- access tokens (Facebook, Cloudflare, Google)
- service account JSON
- cookies/session data
- private URLs, webhook secrets
- `.env` with real values

### 2.2 Where secrets must live
- **Local dev:** `.env` (uncommitted) or local secrets store
- **Cloudflare (prod/staging):** Wrangler secrets
  - `wrangler secret put <NAME>`

### 2.3 Logging secrets is forbidden
- Never log token values.
- If needed for debugging, log only:
  - `token_prefix` (first 4 chars)
  - `token_suffix` (last 4 chars)
- Never log entire request headers.

### 2.4 Rotation & revocation
- Tokens must be revocable and rotated.
- If leakage is suspected:
  - revoke immediately
  - rotate secrets
  - invalidate sessions
  - record incident in `docs/RUNBOOK.md`

---

## 3) Access control

### 3.1 Public vs admin endpoints
**Public endpoints** (read-only) must be safe:
- `GET /api/feed`
- `GET /api/story/:id`
- `GET /api/health`

**Admin endpoints** (if any):
- must be disabled by default in prod
- must require strong auth (shared secret or signed request)
- must never expose secrets in responses

### 3.2 Principle of least privilege
- Facebook permissions: only what is needed to post to our page.
- Translation provider keys: only required scopes.
- D1: only required bindings per environment.

---

## 4) Safe networking (fetch policy)

### 4.1 Allowed fetch targets
Workers should fetch only:
- domains from `sources/registry.yaml`
- explicitly allowed API endpoints (translation provider, Facebook Graph API)

### 4.2 Block SSRF patterns
- Reject:
  - `localhost`, `127.0.0.1`, `0.0.0.0`
  - private IP ranges (10/8, 172.16/12, 192.168/16)
  - link-local addresses
- Reject non-http(s) schemes.
- Do not follow redirects to disallowed hosts.

### 4.3 Timeouts & limits
- Apply request timeouts.
- Limit response sizes for HTML downloads.
- Parse defensively; treat input as hostile.

---

## 5) Input handling & injection safety

### 5.1 HTML sanitization
- Never render raw untrusted HTML in the web UI.
- Store only sanitized snippets (or plain text) in D1.
- If HTML is stored internally for parsing, it must not be exposed publicly.

### 5.2 SQL injection
- Use parameterized queries only.
- Never concatenate user input into SQL strings.
- Validate/whitelist sort keys and filters.

### 5.3 XSS
- Web frontend must escape all text by default.
- Ensure OG tags and meta fields are properly escaped.

---

## 6) Concurrency & data integrity

### 6.1 Cron lock required
- All Cron runs must acquire a **lease-based lock** in D1.
- The lock has a TTL and must be renewed only within the run budget.
- If lock exists and lease is valid, the run exits without doing work.

### 6.2 Idempotency invariants
- Items are uniquely keyed (sha256 normalized URL).
- Stories are deterministically matched or keyed.
- Crosspost states prevent duplicate posts.

### 6.3 Migrations safety
- All schema changes go through `db/migrations/`.
- Avoid destructive migrations.
- Document any risky migrations and provide runbook steps.

---

## 7) Dependency & supply-chain policy

### 7.1 Lockfile required
- `pnpm-lock.yaml` must be committed and kept up-to-date.
- CI must use lockfile to ensure reproducible installs.

### 7.2 Minimal dependencies
- Avoid adding heavy or risky dependencies.
- Prefer small, maintained libraries.

### 7.3 Vulnerability management
- Use Dependabot (optional) and/or periodic audits.
- Security patches should be isolated PRs with clear changelogs.

---

## 8) Data privacy & retention

### 8.1 PII default: NO
- Do not collect user PII.
- Do not store Facebook user data.
- Do not track individuals.

### 8.2 Content retention
- Store minimal text needed for processing:
  - title + short snippet
- Do not store full article bodies by default.
- Truncate stored snippets and logged fragments.

---

## 9) CI/CD and operational safety

### 9.1 CI must not deploy by default
- CI is for validation only (lint/typecheck/tests).
- Deployment requires explicit human action.

### 9.2 Secrets in CI
- If CI uses secrets (e.g., for staging), they must be stored in GitHub Actions secrets.
- Never echo secrets in CI logs.

---

## 10) Security acceptance checklist

A PR is security-acceptable if:
- No secrets introduced (repo, logs, client).
- Fetch targets are validated and SSRF-protected.
- SQL is parameterized; no injection vectors.
- Cron lock and idempotency invariants preserved.
- Any new dependency is justified and pinned via lockfile.
- Documentation updated if security posture changes.

---

## 11) Incident response (minimal)

If an incident occurs (token leak, unauthorized post, data corruption):
1) Contain: revoke/rotate tokens, disable posting, pause Cron.
2) Assess: identify scope, affected runs, affected data.
3) Recover: restore from backups (if needed), replay safe steps.
4) Prevent: add tests/guards, update runbook and policies.
