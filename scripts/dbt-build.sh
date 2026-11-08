#!/usr/bin/env bash
# The one way to run `dbt build`: by hand, in CI (Stage 7) and from Dagster (Stage 5).
#
#   scripts/dbt-build.sh                      # warehouse (downloaded data)
#   scripts/dbt-build.sh test                 # warehouse_test (offline sample)
#   scripts/dbt-build.sh test --select cities # anything after the target goes to dbt
#
# Sets GIT_COMMIT, which the snapshots record on every new row (transform/snapshots/),
# so a snapshot row says which commit's seeds produced it:
#   - an already-set GIT_COMMIT wins (CI and Docker images without .git pass it in);
#   - otherwise the HEAD commit, with "-dirty" when tracked files have uncommitted changes
#     (the seeds on disk are then not exactly that commit's);
#   - "unknown" if git is unavailable.
# Reads .env when present (local runs); CI provides the same variables in its environment.
set -euo pipefail
cd "$(dirname "$0")/.."

target="${1:-warehouse}"
[[ $# -gt 0 ]] && shift
case "$target" in
  warehouse|test) ;;
  *) echo "usage: $0 [warehouse|test] [dbt build options...]" >&2; exit 2 ;;
esac

if [[ -z "${GIT_COMMIT:-}" ]]; then
  if commit="$(git rev-parse HEAD 2>/dev/null)"; then
    [[ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]] && commit="${commit}-dirty"
    GIT_COMMIT="$commit"
  else
    GIT_COMMIT="unknown"
  fi
fi
export GIT_COMMIT
echo "dbt build --target ${target}  (GIT_COMMIT=${GIT_COMMIT})" >&2

env_file=()
[[ -f .env ]] && env_file=(--env-file .env)
exec uv run "${env_file[@]}" dbt build --project-dir transform --profiles-dir transform --target "$target" "$@"
