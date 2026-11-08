#!/usr/bin/env bash
# Prints the GIT_COMMIT that dbt records on every new snapshot row (transform/snapshots/).
# The one rule, shared by scripts/dbt-build.sh and Dagster (orchestration/dbt.py):
#   - an already-set GIT_COMMIT wins (CI, and Docker images without .git, pass it in);
#   - otherwise the HEAD commit, with "-dirty" when tracked files have uncommitted changes
#     (the seeds on disk are then not exactly that commit's);
#   - "unknown" if git is unavailable.
set -euo pipefail
if [[ -n "${GIT_COMMIT:-}" ]]; then
  echo "$GIT_COMMIT"
  exit 0
fi
cd "$(dirname "$0")/.."
if commit="$(git rev-parse HEAD 2>/dev/null)"; then
  [[ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]] && commit="${commit}-dirty"
  echo "$commit"
else
  echo "unknown"
fi
