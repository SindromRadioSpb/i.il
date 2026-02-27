# docs/SECURITY_THREATS.md — Concrete Threats & Controls

This document complements `docs/SECURITY.md` with concrete “what to block” rules.

## 1) SSRF threats (Worker fetch)
**Threat:** attacker-controlled URL leads Worker to fetch internal networks or metadata endpoints.

**Controls (mandatory):**
- Allowlist hosts to:
  - domains from `sources/registry.yaml`
  - known API hosts (translation provider, graph.facebook.com)
- Reject:
  - non-http(s) schemes
  - private IP ranges (10/8, 172.16/12, 192.168/16)
  - localhost and link-local
- Do not follow redirects to disallowed hosts.
- Apply timeouts and max response size.

**Tests (required when fetch code changes):**
- unit tests: rejects localhost/private IP
- unit tests: rejects redirect to private IP

## 2) Token leakage
**Threat:** tokens appear in logs, errors, or client responses.

**Controls:**
- redact tokens in logs
- never log headers
- never return secrets in API responses

**Tests:**
- snapshot test for health/feed/story responses does not include secret-like keys

## 3) SQL injection
**Threat:** concatenating user input into SQL.

**Controls:**
- parameterized queries only
- whitelist sortable fields

**Tests:**
- unit tests for query builder whitelist behavior

## 4) Supply chain
**Threat:** compromised dependency.

**Controls:**
- lockfile required
- minimal dependencies
- dependabot weekly

## 5) Abuse / rate limits
**Threat:** sources or APIs rate-limit us; we get blocked.

**Controls:**
- throttle per source
- exponential backoff with Retry-After
- cap items per run

**Tests:**
- backoff tests with mocked 429/503
