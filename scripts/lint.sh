#!/usr/bin/env bash
set -euo pipefail

pnpm -C apps/worker lint
pnpm -C apps/web lint
