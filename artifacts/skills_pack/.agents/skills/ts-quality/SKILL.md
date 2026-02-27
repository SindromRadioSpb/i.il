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

## Standard workflow (patch steps / tests / DoD)

### Patch steps
1) Identify the affected package(s): worker/web/both.
2) Add or update types first (DTOs, env, API models).
3) Implement code with small functions and explicit return types for core utilities.
4) Add tests before finishing:
   - unit tests for pure logic
   - integration tests for pipelines and API handlers (mock I/O)
5) Run formatting and lint.
6) Run typecheck.
7) Run tests.
8) Update docs if API or behavior changed.

### Tests (commands)
Worker:
- `pnpm -C apps/worker lint`
- `pnpm -C apps/worker typecheck`
- `pnpm -C apps/worker test`

Web:
- `pnpm -C apps/web lint`
- `pnpm -C apps/web typecheck`
- `pnpm -C apps/web test`

### DoD checklist
- [ ] ESLint passes
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] No new `any` (or justified)
- [ ] Public API contract unchanged or updated in docs
- [ ] No secrets/log leaks introduced

---

## Recommended tooling & config (targets)

### TypeScript
- `strict: true`
- `noUncheckedIndexedAccess: true` (optional but recommended)
- `exactOptionalPropertyTypes: true` (optional)

### Lint
- `@typescript-eslint` + recommended rules
- Ban `console.log` in production code (allow in local scripts), or require structured logger wrapper

### Formatting
- Prettier with stable defaults:
  - printWidth 100
  - semi true
  - singleQuote true

### Testing
- Vitest preferred for speed
- Avoid network in unit tests; mock fetch
- Fixtures live under `apps/*/test/fixtures`

---

## Anti-patterns (reject in review)
- “Fix” that adds `any` everywhere to silence errors
- Changing normalization or clustering without tests
- Logging raw payloads (HTML, tokens, credentials)
- Adding dependencies without explaining need and impact
- Breaking API response shapes without updating `docs/API_CONTRACT.md`

---

## Quick scripts (optional)
If repo provides wrappers:
- `scripts/lint.sh`
- `scripts/typecheck.sh`
- `scripts/test.sh`
