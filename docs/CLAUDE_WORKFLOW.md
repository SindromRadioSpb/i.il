# docs/CLAUDE_WORKFLOW.md — How Claude Code Should Work in This Repo

This document makes autonomous work reliable and consistent.

## 1) Mandatory read order
1) `AGENTS.md`
2) `README.md`
3) `docs/SPEC.md`
4) `docs/ARCHITECTURE.md`
5) `docs/ACCEPTANCE.md`
6) `docs/SECURITY.md` + `docs/COMPLIANCE.md`
7) `docs/TEST_PLAN.md`
8) `docs/IMPLEMENTATION_PLAN.md`

## 2) Default execution mode
- Work in small patches (PATCH-01, PATCH-02, …).
- Before coding:
  - restate goal + acceptance criteria
  - enumerate affected modules
  - list risks
  - propose patch steps/tests/DoD
- After coding:
  - run gates (lint/typecheck/test)
  - update docs
  - provide concise change log

## 3) Command policy
Safe commands allowed:
- pnpm install
- lint/typecheck/test
- local dev servers

Commands requiring explicit user instruction:
- deploy (`wrangler deploy`)
- remote migrations
- any operation that posts to Facebook

## 4) No-guess zones
Do not guess and ship on:
- copyright/compliance interpretations
- token/permission scopes for Facebook
- destructive migrations
- API breaking changes

When unsure:
- document the assumption in `docs/DECISIONS.md`
- choose the safest default
- implement behind feature flag if needed

## 5) Quality bar
- deterministic behavior (stable sort, stable hashes)
- idempotent cron
- summary-only publication with attribution
- observable runs and errors
