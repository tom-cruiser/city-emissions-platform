#!/bin/bash
# Creates the `dagster` database: Dagster's own run, schedule and event-log storage.
# It is NOT part of the warehouse: no PostGIS, no layers, no warehouse roles.
#
#   dagster (role) -> owns the dagster database; cannot CONNECT to warehouse or warehouse_test
#   pipeline, api_reader and the test roles -> cannot CONNECT to dagster
#
# Both directions rely on CONNECT being revoked from PUBLIC: here for `dagster`, in
# lib/layers.sql for the warehouses.
#
# Runs automatically on an empty volume. On an existing volume, run it once by hand:
#   docker compose up -d db   # recreates the container so it sees the DAGSTER_PG_* variables
#   docker compose exec db bash /docker-entrypoint-initdb.d/03-dagster-db.sh
# It is safe to re-run: every step checks whether it has already been done.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dagster_db="$DAGSTER_PG_DB" -v dagster_user="$DAGSTER_PG_USER" \
  -v dagster_password="$DAGSTER_PG_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'dagster_user', :'dagster_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'dagster_user') \gexec

-- CREATE DATABASE cannot run inside a transaction or a DO block, hence \gexec.
SELECT format('CREATE DATABASE %I OWNER %I', :'dagster_db', :'dagster_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'dagster_db') \gexec

REVOKE CONNECT ON DATABASE :"dagster_db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dagster_db" TO :"dagster_user";
SQL

# Dagster creates its tables in `public` on first start; the owner role may do that.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DAGSTER_PG_DB" \
  -v dagster_user="$DAGSTER_PG_USER" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CREATE, USAGE ON SCHEMA public TO :"dagster_user";
SQL
