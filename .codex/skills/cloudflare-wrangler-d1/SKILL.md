# .agents/skills/cloudflare-wrangler-d1/SKILL.md — Wrangler + D1 Pack

## Purpose
Provide a safe, repeatable workflow for:
- configuring Wrangler for Workers + D1
- applying migrations to remote D1
- binding DB safely
- avoiding production-impacting commands without explicit user intent

## Golden rules
- All schema changes are migration-driven (`db/migrations/*`).
- No remote migrations or deploys unless user explicitly requested.
- Cron handlers must be idempotent and lock-protected.

---

## Infrastructure (actual IDs — do not change without user approval)

| Resource | Name | ID |
|----------|------|----|
| Worker | `iil` | deployed at `iil.sindromradiospb.workers.dev` |
| D1 dev | `news_hub_dev` | `3e74b9fd-b0b3-4022-ac3d-d08306015420` (WEUR) |
| D1 prod | `news_hub_prod` | `32403483-6512-4673-aaff-a3a6e3c9aad3` (WEUR) |
| Wrangler config | `apps/worker/wrangler.toml` | name = `"iil"` |

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
   - file naming: `NNN_description.sql`
4) Update `db/schema.sql` snapshot if used.
5) Add tests for DB invariants:
   - unique constraints exist
   - repo methods do not produce duplicates
6) Ensure run lock is used by cron ingestion.

### Migration apply commands (HUMAN must approve — never run autonomously)

Apply to **dev** D1:
```bash
npx wrangler d1 execute news_hub_dev --local --file db/migrations/<NNN_name.sql>
```

Apply to **production** D1 (requires explicit user approval):
```bash
npx wrangler d1 execute news_hub_prod --remote --file db/migrations/<NNN_name.sql>
```

**IMPORTANT:** Do NOT use `wrangler d1 migrations apply` — the `migrations` directory is `db/migrations/`, not `apps/worker/migrations/`, so Wrangler's built-in migrations command would fail (exit 127) or apply wrong files. Always use `wrangler d1 execute --file`.

### Deploy command (requires explicit user approval)
```bash
npx wrangler deploy --env production --config apps/worker/wrangler.toml
```

### Tests
- Worker unit tests for migration presence (string checks) and repo functions
- Commands:
  ```bash
  pnpm -C apps/worker lint
  pnpm -C apps/worker typecheck
  pnpm -C apps/worker test
  ```

### DoD checklist
- [ ] D1 binding exists and is named consistently in code (`env.DB`)
- [ ] New tables/columns are created only via migrations
- [ ] Unique constraints enforce idempotency
- [ ] Cron lock exists and prevents overlap
- [ ] No remote-impacting commands executed without user approval

---

## Common pitfalls & fixes

### "D1 binding is undefined"
- Ensure `wrangler.toml` includes correct `d1_databases` binding name.
- Ensure code uses `env.DB` with correct type definition in `src/index.ts`.

### "wrangler d1 migrations apply — exit 127 or wrong directory"
- This project stores migrations in `db/migrations/`, not `apps/worker/migrations/`.
- Always use `wrangler d1 execute --file db/migrations/<file>.sql`.

### "Overlapping cron runs"
- Add a lease lock (`run_lock` table) with TTL < cron interval.
- Exit gracefully if lease is valid.
- Lock TTL = `parseInt(env.CRON_INTERVAL_MIN, 10) * 60 * 1000` ms.

### "ctx.waitUntil run becomes orphaned"
- When cron is triggered via HTTP handler (`POST /api/v1/admin/cron/trigger`), the Worker
  may be killed before `finally` runs, leaving `runs.status='in_progress'` forever.
- Scheduled cron triggers (`[triggers] crons = [...]`) always complete `finally` block.
- To clean up orphaned runs:
  ```sql
  UPDATE runs
  SET status = 'failure', finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
  WHERE status = 'in_progress'
    AND started_at < strftime('%Y-%m-%dT%H:%M:%SZ', datetime('now', '-10 minutes'));
  ```

### "ISO timestamp comparison failures in SQLite"
- D1/SQLite `datetime('now')` returns format `2026-02-28 14:21:42` (space separator).
- Worker code uses `new Date().toISOString()` which returns `2026-02-28T14:21:42.444Z` (T + Z).
- For SQL comparisons, use: `strftime('%Y-%m-%dT%H:%M:%SZ', datetime('now', '-N minutes'))`.

### "Slow queries"
- Add indexes for feed ordering and join paths:
  - `stories(state, last_update_at)`
  - `story_items(story_id, rank)`
  - `items(source_id, published_at)`

---

## Anti-patterns
- Editing D1 schema manually without migrations
- Dropping tables/columns in migrations without decision + runbook
- Building SQL with string concatenation (use `.bind()` always)
- Running `wrangler deploy` or remote migrations without explicit user instruction
- Using `wrangler d1 migrations apply` — wrong directory, use `wrangler d1 execute --file`
