#!/usr/bin/env bash
# scripts/verify_repo.sh — Verify all required repo files are present.
# Run this at the start of any autonomous session before making changes.
# Exit code 0 = all present; non-zero = missing files (print list and fail).
set -euo pipefail

ERRORS=0

check() {
  local f="$1"
  if [ ! -e "$f" ]; then
    echo "MISSING: $f"
    ERRORS=$((ERRORS + 1))
  fi
}

echo "== verify_repo.sh: checking required files =="

# Root
check "AGENTS.md"
check "README.md"
check ".env.example"
check "package.json"
check "pnpm-workspace.yaml"
check "tsconfig.base.json"
check "pnpm-lock.yaml"

# GitHub
check ".github/workflows/ci.yml"
check ".github/dependabot.yml"
check ".github/CODEOWNERS"

# Worker
check "apps/worker/package.json"
check "apps/worker/wrangler.toml"
check "apps/worker/tsconfig.json"
check "apps/worker/eslint.config.js"
check "apps/worker/src/index.ts"
check "apps/worker/src/router.ts"
check "apps/worker/test/health.test.ts"

# Web
check "apps/web/package.json"
check "apps/web/tsconfig.json"
check "apps/web/eslint.config.js"
check "apps/web/astro.config.mjs"
check "apps/web/src/pages/index.astro"

# Database
check "db/migrations/001_init.sql"
check "db/schema.sql"

# Sources
check "sources/registry.yaml"

# Scripts
check "scripts/ci.sh"
check "scripts/format.sh"
check "scripts/lint.sh"
check "scripts/test.sh"
check "scripts/typecheck.sh"
check "scripts/dev.sh"
check "scripts/verify_repo.sh"
check "scripts/verify_env.sh"

# Core docs
check "docs/SPEC.md"
check "docs/ARCHITECTURE.md"
check "docs/ACCEPTANCE.md"
check "docs/API_CONTRACT.md"
check "docs/DB_SCHEMA.md"
check "docs/SECURITY.md"
check "docs/COMPLIANCE.md"
check "docs/QUALITY_GATES.md"
check "docs/OBSERVABILITY.md"
check "docs/RUNBOOK.md"
check "docs/TEST_PLAN.md"
check "docs/IMPLEMENTATION_PLAN.md"
check "docs/DECISIONS.md"
check "docs/CHANGELOG.md"
check "docs/ROADMAP.md"
check "docs/BRAND.md"
check "docs/AUTONOMY_CHECKLIST.md"
check "docs/CONFIG_REFERENCE.md"
check "docs/OPS_AUTOMATION.md"
check "docs/CLAUDE_WORKFLOW.md"
check "docs/EDITORIAL_STYLE.md"
check "docs/GLOSSARY.md"
check "docs/SOURCE_PARSING_GUIDE.md"
check "docs/LOCAL_DEV_GUIDE.md"

# Skills
check ".agents/skills/news-pipeline/SKILL.md"
check ".agents/skills/ts-quality/SKILL.md"
check ".agents/skills/cloudflare-wrangler-d1/SKILL.md"
check ".agents/skills/facebook-publisher/SKILL.md"

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "== verify_repo.sh: ALL PRESENT (OK) =="
  exit 0
else
  echo "== verify_repo.sh: $ERRORS MISSING FILE(S) — fix before proceeding =="
  exit 1
fi
