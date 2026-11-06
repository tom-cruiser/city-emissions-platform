#!/bin/bash
# Creates warehouse_test: same layers as the real warehouse, separate roles.
#
#   test_pipeline    -> owns the test layers (used by pytest for ingestion, later dbt)
#   test_api_reader  -> SELECT on test reporting only (used by the API tests)
#
# Neither test role can CONNECT to the real warehouse, so a misconfigured test
# fails with "permission denied" instead of touching real data.
#
# Runs automatically on an empty volume. On an existing volume, run it once by hand:
#   docker compose up -d   # recreates the container so it sees the TEST_* variables
#   docker compose exec db bash /docker-entrypoint-initdb.d/02-test-db.sh
# It is safe to re-run: every step checks whether it has already been done.
set -euo pipefail

admin_psql() { psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" "$@"; }

admin_psql --dbname "$POSTGRES_DB" \
  -v test_db="$TEST_POSTGRES_DB" -v real_db="$POSTGRES_DB" \
  -v pipeline_user="$TEST_PIPELINE_USER" -v pipeline_password="$TEST_PIPELINE_PASSWORD" \
  -v api_user="$TEST_API_READER_USER" -v api_password="$TEST_API_READER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'pipeline_user', :'pipeline_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'pipeline_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'api_user', :'api_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'api_user') \gexec

-- CREATE DATABASE cannot run inside a transaction or a DO block, hence \gexec.
SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db') \gexec

-- Also close the real warehouse to PUBLIC. Volumes created before this script
-- existed did not do this, so apply it here too (it is idempotent).
REVOKE CONNECT ON DATABASE :"real_db" FROM PUBLIC;
SQL

admin_psql --dbname "$TEST_POSTGRES_DB" \
  -v db_name="$TEST_POSTGRES_DB" -v owner_role="$TEST_PIPELINE_USER" -v reader_role="$TEST_API_READER_USER" \
  -f /docker-entrypoint-initdb.d/lib/layers.sql
