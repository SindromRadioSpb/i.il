# docs/DECISIONS.md — Architectural & Product Decisions (ADR-lite)

This file records key decisions and the rationale behind them.
Format: **Decision**, **Status**, **Context**, **Decision**, **Consequences**, **Notes**.

---

## D-001: Canonical Hub + Crossposting (not “Facebook-first”)
**Status:** Accepted

### Context
A Facebook-first ingestion approach is fragile (permissions/review constraints) and risks non-compliance if implemented via scraping. We also need a portfolio-grade product with strong SEO, long-term content value, and multi-channel distribution.

### Decision
Make the website the **canonical source of truth**. Social platforms (Facebook Page, etc.) are distribution channels that link back to canonical story URLs.

### Consequences
- Stable architecture and long-term value (SEO + archive).
- Crossposting is idempotent and measurable.
- We are less dependent on a single platform’s ingestion constraints.

### Notes
Facebook UI scraping is explicitly forbidden (see COMPLIANCE).

---

## D-002: Cloudflare A1 stack (Pages + Workers Cron + D1)
**Status:** Accepted

### Context
We want minimal infra cost, global distribution, and an event-driven scheduled pipeline with a simple relational store.

### Decision
Use:
- Cloudflare Pages for frontend
- Cloudflare Workers for API + Cron pipeline
- Cloudflare D1 for durable relational state

### Consequences
- Low fixed cost, fast iteration.
- Need careful DB schema + migrations.
- Must design Cron runs to be idempotent and lock-protected.

---

## D-003: Summary-only publication (copyright & compliance)
**Status:** Accepted

### Context
Republishing full source articles violates copyright and invites takedowns.

### Decision
Publish only original Russian summaries plus attribution and links to sources. Do not publish full source text.

### Consequences
- Lower legal risk.
- Better editorial value (we add transformation).
- Requires summary generation logic and quality guards.

---

## D-004: “Sources as code” registry (sources/registry.yaml)
**Status:** Accepted

### Context
We want deterministic coverage, reviewable source additions, and repeatability.

### Decision
Manage sources via `sources/registry.yaml` in version control, with tests/fixtures per source type.

### Consequences
- Transparent coverage and change tracking.
- Requires tooling and fixtures to keep parser stable.

---

## D-005: Cron idempotency with D1 lease locks
**Status:** Accepted

### Context
Scheduled runs can overlap due to delays, deployments, or retries, causing duplicates.

### Decision
Implement a D1-based lease lock (RunLock) for the Cron pipeline. Enforce unique keys (`item_key`) and idempotent publication state.

### Consequences
- Strong protection from duplicates.
- Adds a small amount of DB complexity.
- Requires tests for lock behavior.

---

## D-006: Cost control via clustering + summary-sized translation inputs
**Status:** Accepted

### Context
Translating full articles is expensive and unnecessary. Scenario A targets 50/day with minimal spend.

### Decision
Translate and generate summaries using:
- clustering to avoid duplicates
- short source snippets (1,200–2,000 chars max per item)
- translation memory / hashing to reuse outputs

### Consequences
- Translation costs remain near free-tier under typical loads.
- Requires memoization and careful text selection.
- Summary quality depends on extraction robustness.

---

## D-007: Facebook crossposting via official API only
**Status:** Accepted

### Context
Scraping Facebook is not acceptable; we only need posting to our own Page.

### Decision
Use official Pages API to post to our Page. Store `fb_post_id` and status for idempotency.

### Consequences
- Reliable and compliant.
- Requires token management and permission setup.
- Must handle rate limiting and auth errors robustly.

---

## D-008: Minimal data retention (no full article bodies by default)
**Status:** Accepted

### Context
Storing full article content increases compliance risk and data handling surface area.

### Decision
Store only:
- normalized URL
- title
- short snippet for processing (truncated)
- RU summary
- timestamps and state

### Consequences
- Lower risk and lower storage needs.
- Some advanced NLP features require optional expansions later (feature flagged).

---

## D-009: Admin endpoints are dev-only and gated
**Status:** Accepted

### Context
Manual triggers and rebuilds help debugging, but must not be public in production.

### Decision
Admin endpoints (manual cron, rebuild story) are:
- disabled by default in prod
- gated by secret/signed request in dev

### Consequences
- Safer operations.
- Slight extra work for local tooling.

---

## D-010: Prefer deterministic, testable heuristics before embeddings
**Status:** Accepted

### Context
Embeddings improve clustering but add cost/complexity and reduce determinism.

### Decision
Start with deterministic heuristics (token overlap + time window + separators). Add embeddings later behind a feature flag.

### Consequences
- Faster MVP with strong test coverage.
- Later upgrade path without breaking baseline behavior.

---

## Future decisions (placeholders, not yet accepted)
- Multi-channel publishing (Telegram/WhatsApp) using the same Publication model.
- Optional “human review queue” for `risk_level=high`.
- Embeddings provider and caching strategy.
