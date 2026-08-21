#!/usr/bin/env bash
# Add the CI workflow once the GitHub token has the `workflow` scope.
#
# GitHub refuses to let an OAuth app create or change files under
# .github/workflows/ unless the token carries that scope, so the workflow was
# held back from the first push rather than blocking the deploy.
#
#   gh auth refresh -s workflow      # opens a browser, ~20 seconds
#   ./scripts/enable_ci.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! gh auth status 2>&1 | grep -q "workflow"; then
  echo "The token still lacks the 'workflow' scope."
  echo "Run:  gh auth refresh -s workflow"
  exit 1
fi

# Stop ignoring the workflow directory, and restore the file.
python3 - <<'PY'
import pathlib
p = pathlib.Path(".gitignore")
lines = p.read_text().splitlines(keepends=True)
keep = [
    line for line in lines
    if ".github/workflows/" not in line and "workflow` scope" not in line
    and "Restore with:" not in line
]
p.write_text("".join(keep).rstrip("\n") + "\n")
PY

mkdir -p .github/workflows
cp .ci-pending/ci.yml .github/workflows/ci.yml
rm -rf .ci-pending

git add .gitignore .github/workflows/ci.yml
git rm -r --cached .ci-pending -q 2>/dev/null || true
git commit -q -m "Enable CI: ruff, mypy --strict, pytest, vitest, preflight

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push origin main
echo "CI enabled. Actions will run on the next push."
