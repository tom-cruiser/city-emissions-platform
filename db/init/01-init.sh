#!/bin/bash
# Runs once, on first start with an empty data volume (postgres image convention).
# Sets up the extension, the three warehouse layers and the access model.
#
# Access model: the database enforces "the API never reads raw", not just code review.
#   pipeline    -> owns raw, modelled, reporting (ingestion, dbt, Dagster)
#   api_reader  -> SELECT on reporting only; no access at all to raw or modelled
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v pipeline_user="$PIPELINE_USER" \
  -v pipeline_password="$PIPELINE_PASSWORD" \
  -v api_user="$API_READER_USER" \
  -v api_password="$API_READER_PASSWORD" \
  -v db_name="$POSTGRES_DB" <<'SQL'

-- PostGIS adds geometry/geography types and spatial functions (ST_Area, ST_AsGeoJSON...).
CREATE EXTENSION IF NOT EXISTS postgis;

-- Roles. LOGIN roles with passwords from the environment.
CREATE ROLE :"pipeline_user" LOGIN PASSWORD :'pipeline_password';
CREATE ROLE :"api_user"      LOGIN PASSWORD :'api_password';

-- Nobody gets to create objects in "public" by accident.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO :"pipeline_user", :"api_user";

-- The three layers. Owned by the pipeline role so dbt can create/replace tables in them.
CREATE SCHEMA raw       AUTHORIZATION :"pipeline_user";
CREATE SCHEMA modelled  AUTHORIZATION :"pipeline_user";
CREATE SCHEMA reporting AUTHORIZATION :"pipeline_user";

COMMENT ON SCHEMA raw       IS 'Source data exactly as loaded, plus dataset version metadata. Append-only.';
COMMENT ON SCHEMA modelled  IS 'Cleaned, typed, conformed data (GPC sectors, tCO2e, crosswalked cities). Built by dbt.';
COMMENT ON SCHEMA reporting IS 'Aggregates and views served by the API. Built by dbt. The only schema api_reader can read.';

-- API: read-only on reporting.
GRANT USAGE ON SCHEMA reporting TO :"api_user";
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO :"api_user";

-- dbt drops and recreates tables on every run, so a one-off GRANT would be lost.
-- Default privileges apply to every FUTURE table the pipeline role creates in reporting.
ALTER DEFAULT PRIVILEGES FOR ROLE :"pipeline_user" IN SCHEMA reporting
  GRANT SELECT ON TABLES TO :"api_user";

SQL
