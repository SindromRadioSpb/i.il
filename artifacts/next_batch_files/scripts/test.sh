#!/usr/bin/env bash
set -euo pipefail

pnpm -C apps/worker test
pnpm -C apps/web test
