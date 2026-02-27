# News Hub (HE→RU) — Cloudflare Pages + Workers Cron + D1

**Purpose:** a professional-grade news hub that ingests Hebrew-language news sources, clusters duplicates into unified “stories”, produces high-quality Russian summaries, publishes them to a website (canonical source of truth), and auto-crossposts to a Facebook Page (and optionally other channels).

This repository is structured so **Claude Code can act like an embedded engineer**: follow rules, run checks, ship changes safely. Start with:
- `AGENTS.md` (working agreements)
- `docs/SPEC.md` (requirements)
- `docs/ARCHITECTURE.md` (system shape)
- `docs/ACCEPTANCE.md` (DoD checklist)
- `docs/SECURITY.md` + `docs/COMPLIANCE.md` (non-negotiables)

---

## Core principles

- **Canonical hub:** the website is the source of truth; social posts link back to the hub.
- **Summary-only:** we publish **original Russian summaries**, not full copyrighted articles.
- **Compliance-first:** no scraping of Facebook UI; only official APIs for posting to our own Page.
- **Low-cost by design:** translate *summary-sized* inputs, dedupe aggressively, and reuse translation memory.
- **Idempotent automation:** Cron ingestion and publishing must be safe to re-run.

---

## Repository layout

```
apps/
  worker/           # Cloudflare Worker: API + Cron ingestion + D1 access
  web/              # Cloudflare Pages frontend (SEO, feed, story pages)
db/
  migrations/       # D1 migrations (forward-only)
  schema.sql        # reference schema snapshot
sources/
  registry.yaml     # “sources as code” registry (Hebrew sources)
docs/
  SPEC.md
  ARCHITECTURE.md
  ACCEPTANCE.md
  TEST_PLAN.md
  SECURITY.md
  COMPLIANCE.md
  OBSERVABILITY.md
  RUNBOOK.md
  DECISIONS.md
scripts/            # convenience wrappers: lint/test/typecheck/dev
AGENTS.md
.env.example
```

---

## Tech stack (A1)

- **Cloudflare Workers**: ingestion, clustering, translation pipeline, crossposting, and the public API.
- **Workers Cron Triggers**: scheduled ingestion (e.g., every 10 minutes) + daily digests.
- **Cloudflare D1**: relational storage (items, stories, publications, runs, errors).
- **Cloudflare Pages**: web frontend (SEO-friendly, canonical URLs, OG tags).

---

## Quick start (local dev)

### 1) Prerequisites
- **Node.js 20+ (LTS recommended)**
- **pnpm 9+**
- **Cloudflare Wrangler** (installed via devDependencies inside `apps/worker`)

> Works on Windows, macOS, Linux. Commands below are shell-agnostic; on Windows you can run them in PowerShell.

### 2) Install dependencies
From repo root:
```bash
pnpm install
```

### 3) Configure environment
Copy and adjust the environment file:
```bash
cp .env.example .env
```

**Important:** do not put secrets in `.env` for production. For Cloudflare, use `wrangler secret put`.

### 4) Start the Worker (API + Cron locally)
```bash
pnpm -C apps/worker dev
```

Expected: Wrangler starts a local server (usually `http://127.0.0.1:8787`).

### 5) Start the web frontend (Pages)
In a second terminal:
```bash
pnpm -C apps/web dev
```

Expected: local web dev server (port depends on the chosen framework), calling the Worker API as configured by `PUBLIC_API_BASE_URL`.

---

## Commands

### Worker (apps/worker)
```bash
pnpm -C apps/worker lint
pnpm -C apps/worker typecheck
pnpm -C apps/worker test
pnpm -C apps/worker dev
```

### Web (apps/web)
```bash
pnpm -C apps/web lint
pnpm -C apps/web typecheck
pnpm -C apps/web test
pnpm -C apps/web dev
```

### Run the full quality gate (recommended before any PR)
```bash
pnpm -C apps/worker lint && pnpm -C apps/worker typecheck && pnpm -C apps/worker test
pnpm -C apps/web lint && pnpm -C apps/web typecheck && pnpm -C apps/web test
```

> The repo also provides wrappers in `scripts/` (see `scripts/` directory). These wrappers must remain thin and deterministic.

---

## Configuration & environment variables

### Local/dev (`.env`)
The web app typically needs:
- `PUBLIC_API_BASE_URL` — base URL of the Worker API (default: `http://127.0.0.1:8787`)

The Worker needs (dev can run with reduced features, but these unlock full behavior):
- `TRANSLATION_PROVIDER` — e.g. `google` (default)
- `GOOGLE_CLOUD_PROJECT_ID` — project id (if using Google Cloud Translate)
- `GOOGLE_CLOUD_LOCATION` — e.g. `global`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` — **DO NOT** store in repo; for Cloudflare use secrets
- `FACEBOOK_PAGE_ID` — your Page ID
- `FACEBOOK_APP_ID` — app id (if needed)
- `FACEBOOK_PAGE_ACCESS_TOKEN` — **secret** (Cloudflare secret)
- `CRON_ENABLED` — `true|false` (dev can disable scheduled runs and trigger manually)

### Production (Cloudflare)
Use Wrangler secrets for all sensitive values:
```bash
# Example (run in apps/worker)
pnpm -C apps/worker wrangler secret put FACEBOOK_PAGE_ACCESS_TOKEN
```

Never commit real tokens, cookies, or credentials. See `docs/SECURITY.md`.

---

## Sources registry (coverage is code)

`sources/registry.yaml` is the authoritative list of sources. It is treated like configuration-as-code:
- stable `id`
- `name`
- `type` (rss/sitemap/html)
- `url`
- `lang: he`
- parser hints (as required by SPEC)
- optional category hints

Add/modify sources via PR, with tests for parser behavior (at least one fixture per source type).

---

## Database (D1) migrations

All schema changes go through `db/migrations/` and must be forward-only.
Local development should apply migrations automatically during dev startup or via a dedicated command (see `apps/worker` docs once implemented).

**Rules:**
- No “ad-hoc” schema edits.
- Every migration must have a clear purpose and be testable locally.
- Avoid destructive migrations; if necessary, document in `docs/DECISIONS.md` and `docs/RUNBOOK.md`.

---

## Facebook crossposting (official only)

We post only to **our own** Facebook Page using the official Pages API permissions. We do not scrape Facebook UI and do not bypass access controls.

Crossposting must be:
- idempotent (store post id + state in DB)
- retry-safe (do not duplicate posts)
- rate-limit aware (backoff on transient errors)

See `docs/COMPLIANCE.md` and `docs/SECURITY.md`.

---

## Observability & operations

Minimum observability requirements:
- structured logs (no secrets, no full article text)
- correlation IDs: `run_id`, `source_id`, `item_id`, `story_id`
- persistent run history in D1 (success/failure stats)

See `docs/OBSERVABILITY.md` and `docs/RUNBOOK.md`.

---

## Testing philosophy

- Unit tests for parsing/normalization/dedupe/clustering primitives.
- Integration tests for “ingest → story → publish state” with mocked network and mocked Facebook API.
- Web tests for feed/story rendering, OG tags, canonical URLs, and API contract compatibility.

See `docs/TEST_PLAN.md`.

---

## Autonomous setup (Claude Code)

This repo is designed for autonomous operation by Claude Code. Before any session:

```bash
bash scripts/verify_repo.sh   # all required files present
bash scripts/verify_env.sh    # local env vars set
bash scripts/ci.sh            # CI gate is green
```

**What the agent does autonomously:** run CI, write/update code, update docs, commit.

**What requires human action:** deploy, remote DB migrations, secrets management, Facebook posting, enabling sources.

See [`docs/AUTONOMY_CHECKLIST.md`](docs/AUTONOMY_CHECKLIST.md) for the full breakdown of safe vs. human-required actions.

See [`docs/CONFIG_REFERENCE.md`](docs/CONFIG_REFERENCE.md) for all environment variables, defaults, and secret management commands.

See [`docs/OPS_AUTOMATION.md`](docs/OPS_AUTOMATION.md) for cron operation, manual triggers, and health monitoring.

---

## Deployment (manual, do not run unless requested)

**Cloudflare Worker deploy:**
- build/typecheck/test locally
- apply D1 migrations (remote) explicitly
- deploy worker with Wrangler

**Cloudflare Pages deploy:**
- build frontend
- publish via Pages pipeline

This repo intentionally avoids automatic “push-to-production” steps. See `docs/RUNBOOK.md`.

---

## Project docs

| Document | Purpose |
|----------|---------|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestones v0.1 → v1.0, features, non-goals, engineering checklist |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Keep-a-Changelog record of all notable changes |
| [`docs/BRAND.md`](docs/BRAND.md) | Brand positioning, voice & tone, disclaimers, attribution and corrections policy |
| [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) | Summary-only rule, attribution requirements, Facebook usage policy |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Secrets policy, network access rules, logging constraints |
| [`docs/SPEC.md`](docs/SPEC.md) | Full product requirements and edge cases |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System shape, data flows, component overview |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Worker public API v1 contract (error codes, cursor encoding, full examples) |
| [`docs/DB_SCHEMA.md`](docs/DB_SCHEMA.md) | D1 schema contract, enums, invariants, migration policy |
| [`docs/CONFIG_REFERENCE.md`](docs/CONFIG_REFERENCE.md) | All environment variables: types, defaults, valid values, secrets |
| [`docs/OPS_AUTOMATION.md`](docs/OPS_AUTOMATION.md) | Cron operation, safe modes, manual triggers, health monitoring |
| [`docs/AUTONOMY_CHECKLIST.md`](docs/AUTONOMY_CHECKLIST.md) | Agent autonomy boundaries: what requires human approval |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architectural decision records (ADR-lite) |
| [`docs/QUALITY_GATES.md`](docs/QUALITY_GATES.md) | Mandatory PR gates (tests, compliance, security, performance) |

---

## License

See `LICENSE`.

---

## Contributing

See `CONTRIBUTING.md` (workflow, branching, quality gates).
