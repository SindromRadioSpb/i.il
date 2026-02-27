# db/ — Database schema and migrations

- `migrations/` contains forward-only D1 migrations.
- `schema.sql` is a reference snapshot.

Local apply (example):
- Use Wrangler D1 commands once your D1 database is created and bound in `apps/worker/wrangler.toml`.

Remote apply must be explicitly requested (see AGENTS.md).
