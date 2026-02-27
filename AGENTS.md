# AGENTS.md — Working Agreements for Claude Code (A1: Cloudflare Pages + Workers + D1)

This repository is designed so Claude Code can operate like an embedded engineer: understand context, follow conventions, run checks, and ship changes safely.

**Read order for Claude Code (always):**
1) `AGENTS.md` (this file) — global rules and workflow
2) `README.md` — how to run, test, deploy
3) `docs/SPEC.md` — requirements + constraints + edge cases
4) `docs/ARCHITECTURE.md` — system shape and data flows
5) `docs/ACCEPTANCE.md` — definition of done (DoD)
6) `docs/SECURITY.md` + `docs/COMPLIANCE.md` — non-negotiable policies
7) `docs/TEST_PLAN.md` — test expectations for changes

> If there is an `AGENTS.override.md`, it overrides this file for local/private environments (never commit secrets).

---

## 0) Project intent (one paragraph)

We run a news content hub (“canonical source of truth”) that ingests Hebrew news sources, produces high-quality Russian summaries, clusters duplicates into single “stories”, publishes them to the website, and auto-crossposts to a Facebook Page (and optionally other channels). The system must minimize human intervention, maximize reliability and compliance, and be presentable as professional portfolio-grade engineering.

**Non-goals:**
- Scraping Facebook UI or bypassing access controls
- Republishing full copyrighted articles verbatim
- Storing or exposing secrets in the repository

---

## 1) Hard rules (non-negotiable)

### 1.1 Security & secrets
- **Never** commit secrets (API keys, tokens, cookies, credentials, private URLs).
- All secrets must be provided via environment variables / Cloudflare secrets.
- Do not log secrets. Redact tokens (show only prefix/suffix).

### 1.2 Compliance & copyright
- Public pages must publish **original Russian summaries**, not full source text.
- Always include attribution and a link to the primary source.
- Store only what is necessary for processing and verification.

### 1.3 Data & privacy
- Avoid storing personal data unless required by SPEC (assume “no PII” by default).
- If a change could introduce PII processing, it must be explicitly described in `docs/SPEC.md` and reviewed.

### 1.4 Determinism
- Prefer deterministic outputs (stable sorting, stable IDs/hashes).
- Migrations must be explicit, versioned, and reproducible.

### 1.5 “No silent breakage”
- Any behavior change requires:
  - test updates/additions (or explicit rationale if not testable),
  - documentation update (SPEC/ACCEPTANCE/DECISIONS if applicable),
  - clear commit message.

---

## 2) Repository conventions (shape and ownership)

### 2.1 Canonical structure
- `apps/worker/` — Cloudflare Workers API + Cron ingestion + D1 access
- `apps/web/` — Cloudflare Pages frontend (SEO, feed, story pages)
- `db/` — D1 schema + migrations
- `sources/registry.yaml` — sources registry (“sources as code”)
- `docs/` — specifications, architecture, policies, runbooks
- `scripts/` — developer workflows (lint/test/typecheck/dev)

### 2.2 “Source of truth” rule
- The website is the canonical representation of each story/item.
- Social posts must link back to the hub.
- The hub stores:
  - source metadata + normalized text snippet for processing
  - generated Russian summary
  - clustering keys and story relations
  - publishing state (web + crosspost)

---

## 3) Claude Code workflow (how to execute tasks)

Claude Code should follow this loop:

### 3.1 Intake checklist (before changing code)
1) Identify the requested feature/bugfix and success criteria (from SPEC/ACCEPTANCE).
2) Identify affected components (worker/web/db/sources/docs).
3) Identify risks:
   - breaking changes, data migration needs, API limits, compliance constraints.
4) Propose a patch plan:
   - **patch steps**
   - **tests**
   - **DoD**
5) Only then implement.

### 3.2 Patch plan format (required)
Every meaningful change must come with:

**Patch steps**
- Step-by-step plan with file paths and expected behavior.

**Tests**
- What to run locally
- What to add/update in automated tests

**DoD (definition of done)**
- Checklist of verifiable outcomes

> If a task is too large, split into PATCH-01/02/03 style increments with their own tests/DoD.

### 3.3 Commit discipline (required)
- Small, reviewable commits.
- Conventional commits preferred:
  - `feat(worker): ...`
  - `fix(web): ...`
  - `chore(db): ...`
  - `test(...): ...`
  - `docs(...): ...`

### 3.4 Documentation updates (required when relevant)
Update docs whenever:
- behavior changes
- new env vars are introduced
- new sources fields/semantics are introduced
- new policies/constraints are added

---

## 4) Command execution policy (safe defaults)

### 4.1 Allowed local commands (default safe)
- Dependency install:
  - `pnpm install`
- Lint / typecheck / test:
  - `pnpm -C apps/worker lint`
  - `pnpm -C apps/worker typecheck`
  - `pnpm -C apps/worker test`
  - `pnpm -C apps/web lint`
  - `pnpm -C apps/web typecheck`
  - `pnpm -C apps/web test`
- Formatting:
  - `pnpm -C apps/worker format`
  - `pnpm -C apps/web format`

### 4.2 Network & deployment commands (require explicit user intent)
Do not run deployment or commands that modify remote state unless the user explicitly requested it:
- `wrangler deploy`
- `wrangler d1 migrations apply --remote`
- Posting to Facebook Page API
- Any command that writes production data

### 4.3 D1 database safety
- Local/dev DB changes are okay.
- Remote D1 modifications require explicit user instruction.

### 4.4 “No surprise” changes
- No mass refactors unless requested or required for the feature.
- No dependency upgrades unless requested; if necessary, isolate them.

---

## 5) Engineering standards (quality bar)

### 5.1 TypeScript & style
- Prefer TypeScript end-to-end for Workers and web.
- Keep APIs typed; avoid `any`.

### 5.2 Error handling
- Handle retries/backoff for fetches (sources, external APIs).
- Fail gracefully and record failure state in DB (don’t lose jobs).

### 5.3 Observability
- Structured logs.
- Include correlation IDs:
  - `run_id` for each Cron run
  - `source_id`, `item_id`, `story_id` where relevant
- Do not log full content bodies; truncate safely.

### 5.4 Performance
- Avoid per-row DB queries; batch operations.
- Prefer D1 queries that are index-friendly.

---

## 6) A1-specific constraints (Cloudflare Pages + Workers + D1)

### 6.1 Workers Cron
- Cron must be idempotent:
  - re-running should not duplicate items/stories
  - use stable hashes/keys for dedupe
- Cron must respect rate limits of sources and external APIs.

### 6.2 D1 schema rules
- All schema changes go through `db/migrations/`.
- Migrations must be forward-only and tested locally.

### 6.3 Pages frontend
- SEO matters: OpenGraph, canonical URLs, clean slugs.
- The frontend should not require privileged secrets; it reads from Worker API.

### 6.4 Facebook crosspost
- Only post from our own app/credentials.
- Never scrape Facebook.
- Store crosspost state so retries are safe.

---

## 7) Testing expectations (minimum bar)

- Unit tests (worker): parsing/normalization/dedupe/clustering primitives.
- Integration tests (worker): ingest → story → publish state → crosspost state (mocked).
- Web tests: rendering + canonical/OG tags.

Required gates before merge:
- lint + typecheck + tests (worker + web)
- migrations apply locally (if schema changed)

---

## 8) If something is unclear

Claude Code must not “guess and ship” on:
- compliance/copyright decisions
- API permissions and posting policy
- schema migrations that might drop data
- anything that writes to production

Document assumptions in `docs/DECISIONS.md` and choose the safest default.
