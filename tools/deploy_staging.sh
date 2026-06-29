#!/usr/bin/env bash
# Deterministic staging deploy wrapper for CI/Linux hosts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python tools/deploy_staging.py "$@"
