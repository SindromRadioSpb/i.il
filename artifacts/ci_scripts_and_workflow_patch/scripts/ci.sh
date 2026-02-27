#!/usr/bin/env bash
set -euo pipefail

echo "== Running full CI gate =="
echo ""

echo "-- Worker: lint"
pnpm -C apps/worker lint
echo "-- Worker: typecheck"
pnpm -C apps/worker typecheck
echo "-- Worker: test"
pnpm -C apps/worker test

echo ""
echo "-- Web: lint"
pnpm -C apps/web lint
echo "-- Web: typecheck"
pnpm -C apps/web typecheck
echo "-- Web: test"
pnpm -C apps/web test

echo ""
echo "== CI gate PASS =="
