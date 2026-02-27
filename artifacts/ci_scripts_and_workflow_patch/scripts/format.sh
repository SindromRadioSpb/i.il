#!/usr/bin/env bash
set -euo pipefail

# Format Worker and Web sources using Prettier.
pnpm -C apps/worker format
pnpm -C apps/web format
