# docs/LOCAL_DEV_GUIDE.md — Local Development Guide (Windows-friendly)

This guide ensures any engineer (or Claude Code) can run the project locally.

## 1) Requirements
- Node.js 20+
- pnpm 9+
- Git

## 2) Install
From repo root:
```bash
pnpm install
```

## 3) Environment
Copy:
```bash
cp .env.example .env
```

Typical local values:
- `PUBLIC_API_BASE_URL=http://127.0.0.1:8787`
- `PUBLIC_SITE_BASE_URL=http://localhost:3000`
- `CRON_ENABLED=false` (recommended; use manual trigger)

## 4) Run Worker
```bash
pnpm -C apps/worker dev
```

Verify:
- open `http://127.0.0.1:8787/api/v1/health`

## 5) Run Web
```bash
pnpm -C apps/web dev
```

Verify:
- open web url (depends on framework)
- feed page renders (may show empty until ingest runs)

## 6) Run tests
```bash
pnpm -C apps/worker lint && pnpm -C apps/worker typecheck && pnpm -C apps/worker test
pnpm -C apps/web lint && pnpm -C apps/web typecheck && pnpm -C apps/web test
```

## 7) Manual ingestion (dev)
If admin endpoints are implemented and enabled:
- set `ADMIN_ENABLED=true` and `ADMIN_SHARED_SECRET` (local only)
- call:
  - `POST /api/v1/admin/cron/run` with header `X-Admin-Secret`

If admin endpoints are not implemented yet:
- run the ingestion function via a local script (future patch).

## 8) Common issues
### 8.1 Port already in use
- Change web dev port or stop the process using it.

### 8.2 Worker has no DB binding
- Check `apps/worker/wrangler.toml` has D1 binding name that matches code types.

### 8.3 CI differs from local
- Ensure `pnpm-lock.yaml` is committed and you run `pnpm install --frozen-lockfile` to reproduce.

## 9) Windows notes
- Use PowerShell or Git Bash.
- All repo scripts should be cross-platform where possible.
