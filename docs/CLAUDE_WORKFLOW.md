# docs/CLAUDE_WORKFLOW.md — How Claude Code Should Work in This Repo

This document makes autonomous work reliable and consistent.

---

## 1) Mandatory read order

Before any session, read in this order:
1. `AGENTS.md`
2. `README.md`
3. `docs/SPEC.md`
4. `docs/ARCHITECTURE.md`
5. `docs/ACCEPTANCE.md`
6. `docs/SECURITY.md` + `docs/COMPLIANCE.md`
7. `docs/TEST_PLAN.md`
8. `docs/IMPLEMENTATION_PLAN.md`
9. `docs/AUTONOMY_CHECKLIST.md` ← what is safe to do autonomously

---

## 2) Session start protocol

Before writing any code or docs:

```bash
bash scripts/verify_repo.sh   # all required files present
bash scripts/verify_env.sh    # local env vars set (if doing local dev)
bash scripts/ci.sh            # current state is green
```

If any check fails, create a PATCH-00 to fix prerequisites before anything else.

---

## 3) Default execution mode

Work in small patches (PATCH-01, PATCH-02, …).

### Before coding — restate and plan:
1. Restate the goal and acceptance criteria from the task
2. Enumerate affected modules (files, types, tests, docs)
3. List risks (see risk matrix below)
4. Propose patch steps, tests, and DoD

### After coding — verify and record:
1. Run `bash scripts/ci.sh` (lint + typecheck + test)
2. Update affected docs (`API_CONTRACT.md`, `DB_SCHEMA.md`, `CHANGELOG.md`, etc.)
3. Commit with conventional commit message
4. Provide concise change summary to user

---

## 4) Risk matrix (check before each patch)

| Risk | When it applies | Required action |
|------|----------------|----------------|
| **API regression** | Changing any response in `router.ts` | Read `docs/API_CONTRACT.md`; update contract + tests atomically |
| **Schema migration** | Any D1 table/column/index change | Create new migration file; human applies `--remote`; document in `docs/DECISIONS.md` |
| **Duplicate data** | Ingestion or clustering changes | Verify `UNIQUE(item_key)` still enforced; add dedupe re-run test |
| **SSRF** | Any outbound fetch added | Validate URL scheme + block private IP ranges |
| **Secret exposure** | Logging, error messages, API responses | Check: no tokens, credentials, or raw content in any output |
| **Facebook double-post** | FB crossposting changes | Confirm idempotency guard (`fb_post_id` + `fb_status`) in place |
| **Workers-types conflict** | Any tsconfig change for worker | Confirm `"lib": ["ES2022"]` — never add `"DOM"` |
| **Cron overrun** | Pipeline performance changes | `duration_ms` target < 50s; verify `MAX_NEW_ITEMS_PER_RUN` cap is enforced |

---

## 5) Command policy

### Safe — allowed without confirmation:
- `pnpm install` / `pnpm -C apps/* lint` / typecheck / test
- `wrangler dev --local` (local only)
- `wrangler d1 execute --local` (local SQLite only)
- `bash scripts/verify_repo.sh` / `verify_env.sh` / `ci.sh`
- Writing/editing files in `docs/`, `scripts/`, `apps/`, `.agents/`

### Requires explicit user instruction:
- `wrangler deploy` (pushes to production)
- `wrangler d1 migrations apply --remote` (modifies remote DB)
- `wrangler secret put` (sets Cloudflare secrets)
- Any operation that posts to Facebook
- Enabling/disabling sources in `sources/registry.yaml`
- Changing cron schedule in `wrangler.toml`

---

## 6) No-guess zones

Do not guess and ship on:
- Copyright / compliance interpretations
- Token / permission scopes for Facebook
- Destructive migrations (DROP, ALTER with data loss)
- API breaking changes (changing existing field names/types)
- Risk level logic for stories (`risk_level` classification)

When unsure:
- Document the assumption in `docs/DECISIONS.md`
- Choose the safest default
- Implement behind feature flag if needed
- Ask the user for explicit approval

---

## 7) Quality bar

Every committed patch must have:
- Deterministic behavior (stable sort, stable hashes, no random IDs in tests)
- Idempotent cron (safe to re-run without side effects)
- Summary-only publication with attribution (see `docs/COMPLIANCE.md`)
- Observable runs and errors (counters, run_id, source_id in logs)
- `bash scripts/ci.sh` passes (lint + typecheck + all tests)

---

## 8) Commit discipline

Conventional commit format: `type(scope): description`

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`
Scopes: `worker`, `web`, `db`, `ci`, `docs`, `infra`, `scripts`

Examples:
```
feat(worker): implement RSS ingestion with dedupe
fix(worker): correct item_key normalization for query strings
docs: add CONFIG_REFERENCE and OPS_AUTOMATION
chore(ci): add verify_repo and verify_env scripts
```

Always include a CHANGELOG entry after each meaningful patch.
