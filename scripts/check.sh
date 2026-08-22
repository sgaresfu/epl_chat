#!/usr/bin/env bash
# Every gate, with real exit codes.
#
# Piping a test run into `tail` reports tail's status, not the suite's — which
# let a red suite through twice. Nothing here is piped.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
run() {
  local label="$1"; shift
  if "$@" > /tmp/check.log 2>&1; then
    printf "  ok    %s\n" "$label"
  else
    printf "  FAIL  %s\n" "$label"
    tail -15 /tmp/check.log | sed 's/^/          /'
    fail=1
  fi
}

echo "backend"
run "ruff"          ./.venv/bin/ruff check shared services tests scripts
run "ruff format"   ./.venv/bin/ruff format --check shared services tests scripts
run "mypy --strict" ./.venv/bin/mypy shared services
run "pytest"        ./.venv/bin/python -m pytest -q
run "data"          ./.venv/bin/python scripts/check_data.py
run "preflight"     ./.venv/bin/python scripts/preflight.py

echo "frontend"
cd apps/web
run "typecheck"     npx tsc --noEmit
run "vitest"        npx vitest run
run "build"         npm run build

echo
if [ "$fail" -eq 0 ]; then echo "ALL GREEN"; else echo "SOMETHING FAILED"; fi
exit "$fail"
