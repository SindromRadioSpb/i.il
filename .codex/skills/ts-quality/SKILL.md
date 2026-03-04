# .agents/skills/ts-quality/SKILL.md — TypeScript Quality Pack

## Purpose
Provide a repeatable procedure for maintaining high TypeScript quality across Worker and Web:
- strict typing
- deterministic formatting
- predictable tests
- minimal regressions

## When to apply
- Any patch that touches TS code in `apps/worker` or `apps/web`.
- Any change that touches API contracts, parsing, clustering, or crossposting.

## Golden rules
- `strict` typing is the default.
- No `any` without justification (documented in code comment + PR description).
- No silent behavior changes: add tests and update docs.
- Keep diffs focused; avoid drive-by refactors.

---

## Pre-patch checklist (run before writing code)

```bash
bash scripts/verify_repo.sh   # all required files present
bash scripts/ci.sh            # current baseline is green
```

If CI is not green, fix it before starting new work.

---

## Risk matrix

| Risk | Trigger | Mitigation |
|------|---------|------------|
| **API regression** | Changing router.ts response shape | Read `docs/API_CONTRACT.md` before any shape change; update contract + tests atomically |
| **Type unsafety** | Using `any` or `as unknown as X` to silence errors | Justify in code comment; prefer proper type narrowing |
| **Workers-types conflict** | Adding DOM lib to worker tsconfig | Worker tsconfig must have `"lib": ["ES2022"]` only — never add `"DOM"` |
| **Test fixture drift** | Fixtures don't reflect current API shape | Keep fixtures in `apps/worker/test/fixtures/`; update when schema changes |
| **Secrets in logs** | Logging env vars or request headers | Never log: tokens, credentials, full headers; see `docs/SECURITY.md` |
| **Breaking Env interface** | Adding/removing worker env vars | Update `Env` type in `src/index.ts` AND `wrangler.toml [vars]` (or document as secret-only) together |
| **Stale CONFIG_REFERENCE** | Adding env vars without updating docs | Update `docs/CONFIG_REFERENCE.md` whenever `Env` interface changes |

---

## Standard workflow (patch steps / tests / DoD)

### Patch steps
1) Identify the affected package(s): worker / web / both.
2) Add or update types first (DTOs, env, API models).
3) Implement code with small functions and explicit return types for core utilities.
4) Add tests before finishing:
   - unit tests for pure logic
   - integration tests for pipelines and API handlers (mock I/O)
   - fixtures under `apps/*/test/fixtures/`
5) Run formatting and lint.
6) Run typecheck.
7) Run tests.
8) Update docs if API or behavior changed.

### Tests (commands)
Worker:
```bash
pnpm -C apps/worker lint
pnpm -C apps/worker typecheck
pnpm -C apps/worker test
```

Web:
```bash
pnpm -C apps/web lint
pnpm -C apps/web typecheck
pnpm -C apps/web test
```

Full gate:
```bash
bash scripts/ci.sh
```

### DoD checklist
- [ ] ESLint passes (no warnings promoted to errors)
- [ ] Typecheck passes (`tsc --noEmit`)
- [ ] Tests pass (all suites green, currently 215+ tests in worker)
- [ ] No new `any` (or justified with comment)
- [ ] Public API contract unchanged, or `docs/API_CONTRACT.md` updated
- [ ] No secrets / log leaks introduced
- [ ] Worker tsconfig still has `"lib": ["ES2022"]` (no DOM)
- [ ] `docs/CHANGELOG.md` updated

---

## Post-patch checklist

```bash
bash scripts/ci.sh   # green
```

---

## Recommended tooling & config (targets)

### TypeScript
- `strict: true`
- `noUncheckedIndexedAccess: true` (optional but recommended)
- `exactOptionalPropertyTypes: true` (optional)
- Worker tsconfig: `"lib": ["ES2022"]` — never `"DOM"` (conflicts with `@cloudflare/workers-types`)

### Lint
- `@typescript-eslint` parser (flat config, ESLint v9)
- Ban `console.log` in production code (allow in local scripts), or require structured logger wrapper

### Formatting
- Prettier with stable defaults:
  - printWidth 100
  - semi true
  - singleQuote true

### Testing
- Vitest preferred for speed
- Avoid network in unit tests; mock fetch
- Fixtures live under `apps/*/test/fixtures/`

---

## Anti-patterns (reject in review)
- "Fix" that adds `any` everywhere to silence errors
- Changing normalization or clustering without tests
- Logging raw payloads (HTML, tokens, credentials)
- Adding dependencies without explaining need and impact
- Breaking API response shapes without updating `docs/API_CONTRACT.md`
- Adding `"DOM"` to worker tsconfig (breaks workers-types v4)
- Using `@ts-expect-error` without a comment explaining why
