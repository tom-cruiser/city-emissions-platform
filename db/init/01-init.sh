#!/bin/bash
# Runs once, on first start with an empty data volume (postgres image convention).
# Creates the real warehouse's roles, then its layers via lib/layers.sql.
#
# Access model: the database enforces "the API never reads raw", not just code review.
#   pipeline    -> owns raw, modelled, reporting (ingestion, dbt, Dagster)
#   api_reader  -> SELECT on reporting only; no access at all to raw or modelled
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v pipeline_user="$PIPELINE_USER" -v pipeline_password="$PIPELINE_PASSWORD" \
  -v api_user="$API_READER_USER" -v api_password="$API_READER_PASSWORD" <<'SQL'
CREATE ROLE :"pipeline_user" LOGIN PASSWORD :'pipeline_password';
CREATE ROLE :"api_user"      LOGIN PASSWORD :'api_password';
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v db_name="$POSTGRES_DB" -v owner_role="$PIPELINE_USER" -v reader_role="$API_READER_USER" \
  -f /docker-entrypoint-initdb.d/lib/layers.sql
