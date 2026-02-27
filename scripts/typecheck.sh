#!/usr/bin/env bash
set -euo pipefail

pnpm -C apps/worker typecheck
pnpm -C apps/web typecheck
