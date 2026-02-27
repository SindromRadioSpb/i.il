# docs/CHANGELOG.md — News Hub (A1)

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

> **Note:** This project is pre-release. Everything currently lives under `[Unreleased]`.
> When v0.1 ships, this section will be cut into a dated release entry.

---

## [Unreleased]

### Added

#### Web frontend (apps/web)
- `apps/web/src/pages/index.astro`: added try/catch around Worker health fetch so `astro build` succeeds even when Worker is unreachable at build time (static SSG — fetch runs during build)
- `astro build` verified: produces `apps/web/dist/` cleanly

#### Cloudflare deployment config
- `apps/worker/wrangler.toml`: renamed worker `"news-hub-worker"` → `"iil"` (matches Cloudflare project name)
- `wrangler.toml`: added `[env.production.vars]` with explicit production values (CRON_ENABLED/FB_POSTING_ENABLED=false until manually enabled)
- `wrangler.toml`: added `[env.production.triggers]` so cron is registered in production environment (named envs don't inherit top-level triggers)

#### Wrangler v4 upgrade
- `apps/worker/package.json`: wrangler upgraded from `^3.99.0` to `^4.0.0` (installed 4.69.0)
- `pnpm-lock.yaml`: regenerated for wrangler v4 dependency tree
- Verified CI gate (lint/typecheck/test) passes with wrangler v4
- `wrangler.toml`: `[env.production]` section added with `news_hub_prod` D1 binding (`32403483-6512-4673-aaff-a3a6e3c9aad3`, WEUR)
- `news_hub_dev` D1 (remote): all 7 tables present and confirmed via wrangler v4 smoke query
- Local dev (`wrangler dev --local`): Worker starts on `http://127.0.0.1:8787`, D1 binding confirmed, `GET /api/v1/health` returns 200

#### Repo Autonomy Hardening
- `docs/AUTONOMY_CHECKLIST.md`: what user must provide vs. what agent does autonomously vs. human-required actions; Facebook and Google Cloud setup guides; pre-launch checklist
- `docs/CONFIG_REFERENCE.md`: complete reference for all environment variables — types, defaults, valid values, secret flags, environment matrix, secret management commands
- `docs/OPS_AUTOMATION.md`: cron schedule and pipeline breakdown, safe operation modes, manual trigger guide, health endpoint interpretation, run history queries, lock management, FB posting recovery, cost controls, monitoring checklist
- `scripts/verify_repo.sh`: checks all required repo files are present; exit 1 on any missing
- `scripts/verify_env.sh`: checks local dev env vars; distinguishes required vs. optional; loads `.env` automatically
- `docs/CLAUDE_WORKFLOW.md`: expanded with risk matrix (API regression, SSRF, schema, secret exposure, FB double-post, workers-types conflict, cron overrun), session start protocol, pre/post patch checklists, commit discipline guide
- `.agents/skills/news-pipeline/SKILL.md`: added pre/post patch checklists, risk matrix (SSRF, duplicates, API regression, log leakage), fixtures protocol
- `.agents/skills/ts-quality/SKILL.md`: added pre/post patch checklists, risk matrix (workers-types conflict, API regression, secrets in logs), expanded DoD
- `docs/API_CONTRACT.md`: error code table, full error response examples for all status codes (400/401/403/404/500), cursor encoding spec (opaque contract + internal format note)
- `docs/DB_SCHEMA.md`: `snippet_he` max 500 chars, enum enforcement note (SQLite does not enforce CHECK constraints), CHECK constraint pattern recommendation, retention invariant clarified
- `README.md`: "Autonomous setup" section with verify scripts, links to `AUTONOMY_CHECKLIST`, `CONFIG_REFERENCE`, `OPS_AUTOMATION`; expanded "Project docs" table (14 entries)

#### Repository & Toolchain
- Monorepo scaffold: pnpm workspace (`pnpm-workspace.yaml`), shared `tsconfig.base.json`
- Root `package.json` with workspace-level scripts
- `pnpm-lock.yaml` generated and committed (enables `--frozen-lockfile` in CI)
- `.npmrc` with `node-linker=hoisted`, `package-import-method=copy`, `strict-peer-dependencies=false`
- `apps/worker/package.json` — Cloudflare Worker project (`@news-hub/worker`)
- `apps/web/package.json` — Astro Pages project (`@news-hub/web`)

#### CI / GitHub
- `.github/workflows/ci.yml` — GitHub Actions pipeline: Node 20 + pnpm 9, `lint → typecheck → test` for worker and web
- `.github/dependabot.yml` — automated dependency update configuration
- `.github/CODEOWNERS` — repository ownership (`* @SindromRadioSpb`)
- ESLint flat config (`eslint.config.js`) for worker and web (ESLint v9 + `@typescript-eslint/parser`)
- Prettier configured for worker and web

#### Scripts
- `scripts/ci.sh` — full local CI gate (lint + typecheck + test, worker + web)
- `scripts/format.sh` — Prettier formatting for worker and web
- `scripts/lint.sh` — lint runner
- `scripts/test.sh` — test runner
- `scripts/typecheck.sh` — typecheck runner
- `scripts/dev.sh` — dev server launcher

#### Cloudflare Worker (`apps/worker`)
- `src/index.ts` — Worker entry point with `ExportedHandler<Env>`, fetch + scheduled handlers
- `src/router.ts` — API router implementing API v1 skeleton:
  - `GET /api/v1/health` — service info + `last_run` (null until cron runs)
  - `GET /api/v1/feed` — stub returning `{stories:[], next_cursor:null}`
  - `GET /api/v1/story/:id` — stub returning `404 not_found`
- `wrangler.toml` — Cloudflare Worker config: D1 binding (`DB`), cron trigger (`*/10 * * * *`), env vars
- `apps/worker/tsconfig.json` — Worker TS config: `lib:["ES2022"]` to avoid DOM/workers-types conflict
- D1 database `news_hub_dev` created (region WEUR, `database_id` bound in `wrangler.toml`)
- D1 migration `db/migrations/001_init.sql` applied to remote dev database:
  - Tables: `items`, `stories`, `story_items`, `publications`, `runs`, `run_lock`, `error_events`
  - Indexes for query patterns and unique constraints for idempotency

#### Web (`apps/web`)
- `src/pages/index.astro` — feed page placeholder
- `src/pages/story/` — story page directory placeholder
- `astro.config.mjs` — Astro configuration
- `apps/web/tsconfig.json` — web TS config

#### Database
- `db/migrations/001_init.sql` — initial schema: 7 tables, indexes, unique constraints
- `db/schema.sql` — reference schema snapshot
- `db/README.md` — migration workflow documentation

#### Sources Registry
- `sources/registry.yaml` — authoritative list of Hebrew news sources (sources as code)

#### Documentation
- `docs/SPEC.md` — full product requirements and constraints
- `docs/ARCHITECTURE.md` — system shape, data flows, component diagram
- `docs/IMPLEMENTATION_PLAN.md` — PATCH-series autonomous build plan (PATCH-01 → 13 + RC1)
- `docs/API_CONTRACT.md` — Worker public API v1 contract (health / feed / story + admin stubs)
- `docs/ACCEPTANCE.md` — definition of done (DoD) checklist
- `docs/COMPLIANCE.md` — summary-only policy, attribution rules, Facebook usage policy
- `docs/SECURITY.md` — secrets policy, network access rules, logging rules
- `docs/SECURITY_THREATS.md` — threat model and mitigations
- `docs/DECISIONS.md` — architectural decision records (D-001 → D-010)
- `docs/QUALITY_GATES.md` — mandatory PR gates (tests, compliance, security, performance)
- `docs/OBSERVABILITY.md` — structured logging, correlation IDs, run metrics
- `docs/RUNBOOK.md` — operational playbook (deploy, rollback, incident)
- `docs/TEST_PLAN.md` — test strategy and coverage expectations
- `docs/DB_SCHEMA.md` — ERD and schema invariants
- `docs/SOURCE_PARSING_GUIDE.md` — guide for adding and testing new sources
- `docs/EDITORIAL_STYLE.md` — RU summary format and editorial rules
- `docs/GLOSSARY.md` — transliteration glossary (toponyms, names, institutions)
- `docs/LOCAL_DEV_GUIDE.md` — local development setup guide
- `docs/CLAUDE_WORKFLOW.md` — Claude Code task workflow reference
- `docs/DEMO.md` — demo script for portfolio / stakeholder walkthroughs
- `docs/ROADMAP.md` — product milestones and engineering checklist (this release)
- `docs/CHANGELOG.md` — this file
- `docs/BRAND.md` — brand positioning, voice & tone, disclaimers, attribution policy
- `AGENTS.md` — working agreements for Claude Code (task rules, commit discipline)
- `README.md` — project overview, quick start, commands, configuration reference
- `.env.example` — documented environment variables (no secrets)

#### Tests
- `apps/worker/test/health.test.ts` — 6 tests covering API v1 contract:
  - `GET /api/v1/health` full contract shape (ISO-8601, valid env values)
  - `GET /api/v1/feed` empty stories list
  - `GET /api/v1/story/:id` 404 with `story_id` in details
  - 404 fallback for unknown routes

### Changed

- `apps/worker/tsconfig.json`: added `"lib": ["ES2022"]` to resolve conflict between DOM types and `@cloudflare/workers-types@4`
- `apps/worker/src/index.ts`: removed explicit handler param type annotations; rely on `ExportedHandler<Env>` inference to stay compatible across workers-types versions
- `apps/web/package.json`: lint script uses `--no-error-on-unmatched-pattern` (web has `.astro` files only in src, no `.ts` yet); format script uses `--ignore-unknown` (no `prettier-plugin-astro` installed yet)
- `wrangler.toml`: replaced placeholder `database_id` with real D1 binding for `news_hub_dev`

### Fixed

- Broken `node_modules` after pnpm install abort on Windows (sharp rename lock): resolved by full `node_modules` removal + clean reinstall
- ESLint v9 crash (`Cannot find module type-utils`): resolved by removing `@typescript-eslint/eslint-plugin` import from flat configs (parser-only approach)
- `@ts-expect-error` misplaced in test file (TS2578 unused directive): replaced with `{} as unknown as D1Database` cast

### Security

- `.gitignore` excludes `.env`, `*.secret`, `node_modules`, and `.wrangler/` (local D1 state)
- No tokens, credentials, or private URLs committed at any point
- `AGENTS.md` hard rule §1.1: secrets via env / Cloudflare secrets only
- `docs/SECURITY.md` defines redaction policy for logs
