# docs/QUALITY_GATES.md — Mandatory Checks & Standards

This document defines the quality gates that must be satisfied for any PR/patch.
Goal: keep the project portfolio-grade and safe for autonomous work by Claude Code.

If a change conflicts with this document, **this document wins**.

---

## 1) Mandatory gates (must pass)

### 1.1 Worker gates (apps/worker)
Run:
- `pnpm -C apps/worker lint`
- `pnpm -C apps/worker typecheck`
- `pnpm -C apps/worker test`

### 1.2 Web gates (apps/web)
Run:
- `pnpm -C apps/web lint`
- `pnpm -C apps/web typecheck`
- `pnpm -C apps/web test`

### 1.3 Full gate (recommended)
- run both worker and web gates in the same PR.

---

## 2) Required standards

### 2.1 TypeScript strictness
- `strict: true` (or equivalent strict mode).
- Avoid `any`. If unavoidable, isolate and justify.
- Prefer typed API schemas and validators.

### 2.2 Lint + formatting
- ESLint must be configured and enforced.
- Prettier formatting must be consistent.
- No “format-only” changes mixed with logic unless requested.

### 2.3 Tests policy
- Any bug fix requires a regression test.
- Any change to:
  - URL normalization
  - dedupe keys
  - clustering logic
  - summary formatting/guards
  - FB posting logic
  must include tests that prove behavior.

### 2.4 Documentation policy
Update docs when:
- behavior changes (SPEC/ACCEPTANCE)
- API shape changes (API_CONTRACT)
- schema changes (DB_SCHEMA + migrations)
- security/compliance policies change

---

## 3) Compliance gates (non-negotiable)

A PR is rejected if it introduces:
- publishing full source text publicly (must remain summary-only)
- missing attribution (sources list + links)
- Facebook scraping or browser automation for third-party content
- secrets in repo or logs
- increased data retention without explicit decision

---

## 4) Security gates (non-negotiable)

A PR is rejected if:
- it logs tokens/credentials
- it allows SSRF (fetching arbitrary URLs, private IPs)
- it uses string concatenation for SQL with user input
- it adds admin endpoints enabled by default in prod

---

## 5) Performance gates (scenario A baseline)

For scenario A (50/day):
- Cron run time budget: target **< 30 seconds** locally.
- No N+1 DB queries in hot paths (ingest, feed, story detail).
- Max caps enforced:
  - max items per source per run
  - max new items per run

---

## 6) Acceptance gates

For release candidates:
- `docs/ACCEPTANCE.md` must be fully satisfied.
- Demo flow documented and reproducible.

---

## 7) PR checklist (copy/paste)

- [ ] Worker: lint/typecheck/test pass
- [ ] Web: lint/typecheck/test pass
- [ ] No secrets added (repo/logs)
- [ ] Summary-only + attribution preserved
- [ ] API contract updated (if needed)
- [ ] DB migrations added (if schema changed)
- [ ] Regression tests added for behavior change
- [ ] RUNBOOK updated for new failure modes
