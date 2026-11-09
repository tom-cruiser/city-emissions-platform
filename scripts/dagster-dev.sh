#!/usr/bin/env bash
# Dagster locally (UI on http://127.0.0.1:3030 by default), against the Compose database.
#
#   scripts/dagster-dev.sh                 # PIPELINE_TARGET=warehouse (downloads)
#   PIPELINE_TARGET=test scripts/dagster-dev.sh
#
# DAGSTER_HOME is orchestration/ (dagster.yaml: storage in the `dagster` database).
# Its local artifacts (compute logs, ...) go to orchestration/storage/, git-ignored.
set -euo pipefail
cd "$(dirname "$0")/.."
export DAGSTER_HOME="$PWD/orchestration"
export PGHOST="${PGHOST:-localhost}"
env_file=()
[[ -f .env ]] && env_file=(--env-file .env)
exec uv run "${env_file[@]}" dagster dev -m orchestration.definitions \
  --host 127.0.0.1 --port "${DAGSTER_PORT:-3030}" "$@"
