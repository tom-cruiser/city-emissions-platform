#!/usr/bin/env bash
# The one way to run `dbt build` by hand and in CI. Dagster runs dbt through dagster-dbt,
# with the same GIT_COMMIT rule (scripts/git-commit.sh).
#
#   scripts/dbt-build.sh                      # warehouse (downloaded data)
#   scripts/dbt-build.sh test                 # warehouse_test (offline sample)
#   scripts/dbt-build.sh test --select cities # anything after the target goes to dbt
#
# Sets GIT_COMMIT, which the snapshots record on every new row (transform/snapshots/),
# so a snapshot row says which commit's seeds produced it. The rule lives in
# scripts/git-commit.sh, which Dagster uses too.
# Reads .env when present (local runs); CI provides the same variables in its environment.
set -euo pipefail
cd "$(dirname "$0")/.."

target="${1:-warehouse}"
[[ $# -gt 0 ]] && shift
case "$target" in
  warehouse|test) ;;
  *) echo "usage: $0 [warehouse|test] [dbt build options...]" >&2; exit 2 ;;
esac

GIT_COMMIT="$(scripts/git-commit.sh)"
export GIT_COMMIT
echo "dbt build --target ${target}  (GIT_COMMIT=${GIT_COMMIT})" >&2

env_file=()
[[ -f .env ]] && env_file=(--env-file .env)
exec uv run "${env_file[@]}" dbt build --project-dir transform --profiles-dir transform --target "$target" "$@"
