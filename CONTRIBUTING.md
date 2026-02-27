# CONTRIBUTING.md — Workflow & Quality Gates

This repository is designed for professional, portfolio-grade engineering and for effective work with Claude Code.

Start by reading:
- `AGENTS.md`
- `README.md`
- `docs/SPEC.md`
- `docs/ACCEPTANCE.md`
- `docs/SECURITY.md` + `docs/COMPLIANCE.md`

---

## 1) Ground rules

- **No secrets** in commits (tokens, keys, cookies, service account JSON, real `.env`).
- **No Facebook scraping**. Only official posting to our Page.
- **Summary-only** publication with attribution. Never republish full articles.
- Changes must be **small and reviewable**.
- Any behavior change requires **tests** and **docs** updates.

---

## 2) Branching & PRs

### 2.1 Branch naming
Use one of:
- `feat/<short-name>`
- `fix/<short-name>`
- `chore/<short-name>`
- `docs/<short-name>`
- `test/<short-name>`

### 2.2 PR requirements
Every PR must include:
- clear description of the change
- reference to SPEC/ACCEPTANCE items impacted
- tests added/updated (or rationale)
- any migrations (if DB changes)
- screenshots for UI/SEO changes (optional but helpful)

---

## 3) Commit style

Prefer Conventional Commits:
- `feat(worker): ...`
- `fix(web): ...`
- `chore(db): ...`
- `docs: ...`
- `test(worker): ...`

Keep commits focused. Avoid “mega commits” that mix refactors with features.

---

## 4) Local development

Install dependencies:
```bash
pnpm install
```

Run worker:
```bash
pnpm -C apps/worker dev
```

Run web:
```bash
pnpm -C apps/web dev
```

---

## 5) Required quality gate (before pushing)

Run all gates:
```bash
pnpm -C apps/worker lint && pnpm -C apps/worker typecheck && pnpm -C apps/worker test
pnpm -C apps/web lint && pnpm -C apps/web typecheck && pnpm -C apps/web test
```

If you add a new source parser or change extraction logic:
- add/update fixtures in `apps/worker/test/fixtures/`
- add regression tests

---

## 6) Database changes (D1)

- All schema changes go through `db/migrations/`.
- Migrations are forward-only.
- Avoid destructive changes.
- Update `db/schema.sql` snapshot if you maintain one.
- Add tests for any schema-dependent behavior.

---

## 7) Compliance checklist (must pass)

Before merging:
- Public pages show **only RU summaries**, no copied article text.
- Attribution is present (sources list + links).
- Logs contain no secrets and no full article bodies.
- Facebook crossposting uses official API only.
- Admin endpoints (if any) are gated and disabled in prod by default.

---

## 8) Adding a new news source

1) Add the source to `sources/registry.yaml`:
- stable `id`
- type + URL
- throttle and parser hints

2) Add fixtures:
- RSS: `apps/worker/test/fixtures/rss/<source>.xml`
- Sitemap: `.../fixtures/sitemap/<source>.xml`
- HTML: `.../fixtures/html/<source>.html`

3) Add tests to cover parsing and dedupe behavior.

4) Ensure the source respects throttle and max items per run.

---

## 9) Release readiness (portfolio-grade)

A release is ready when:
- All checks are green
- `docs/ACCEPTANCE.md` checklist is satisfied
- `docs/RUNBOOK.md` covers any new operational scenarios
- Demo flow is documented (2-minute WOW demo)

---

## 10) Communication style

Be explicit:
- explain tradeoffs
- document decisions in `docs/DECISIONS.md` when architecture changes
- keep PRs self-contained
