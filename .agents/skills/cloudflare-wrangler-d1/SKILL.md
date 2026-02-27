# .agents/skills/cloudflare-wrangler-d1/SKILL.md — Wrangler + D1 Pack

## Purpose
Provide a safe, repeatable workflow for:
- configuring Wrangler for Workers + D1
- applying migrations locally
- binding DB safely
- avoiding production-impacting commands without explicit user intent

## Golden rules
- All schema changes are migration-driven (`db/migrations/*`).
- No remote migrations or deploys unless user explicitly requested.
- Cron handlers must be idempotent and lock-protected.

---

## Standard workflow (patch steps / tests / DoD)

### Patch steps
1) Update/validate `apps/worker/wrangler.toml`:
   - `d1_databases` binding (e.g., `DB`)
   - `vars` for non-secrets
   - cron triggers (defined but guarded by `CRON_ENABLED`)
2) Implement D1 client wrapper and repos (parameterized queries).
3) Add/modify migrations in `db/migrations/`:
   - forward-only, additive preferred
4) Update `db/schema.sql` snapshot if used.
5) Add tests for DB invariants:
   - unique constraints exist
   - repo methods do not produce duplicates
6) Ensure run lock is used by cron ingestion.

### Tests
- Worker unit tests for migration presence (string checks) and repo functions
- Integration tests can run against local D1 where supported:
  - `wrangler dev` + test harness (optional)

Commands:
- `pnpm -C apps/worker lint`
- `pnpm -C apps/worker typecheck`
- `pnpm -C apps/worker test`

### DoD checklist
- [ ] D1 binding exists and is named consistently in code (`env.DB`)
- [ ] New tables/columns are created only via migrations
- [ ] Unique constraints enforce idempotency
- [ ] Cron lock exists and prevents overlap
- [ ] No remote-impacting commands executed

---

## Common pitfalls & fixes

### “D1 binding is undefined”
- Ensure `wrangler.toml` includes correct `d1_databases` binding name.
- Ensure code uses `env.DB` with correct type definition.

### “Migrations not applied locally”
- Provide a local migration apply step in README or a script.
- Keep migrations deterministic and ordered.

### “Overlapping cron runs”
- Add a lease lock (`run_lock` table) with TTL < cron interval.
- Exit gracefully if lease is valid.

### “Slow queries”
- Add indexes for feed ordering and join paths:
  - `stories(state,last_update_at)`
  - `story_items(story_id,rank)`
  - `items(source_id,published_at)`

---

## Anti-patterns
- Editing D1 schema manually without migrations
- Dropping tables/columns in migrations without decision + runbook
- Building SQL with string concatenation
- Running `wrangler deploy` or remote migrations without explicit instruction
