-- Shared setup for one warehouse database: PostGIS, the three layers, and access.
-- Run with psql against the target database, passing:
--   -v db_name=...  -v owner_role=...  -v reader_role=...
-- Used for both `warehouse` (01-init.sh) and `warehouse_test` (02-test-db.sh), so
-- the test database is built by exactly the same code as the real one.
--
-- (Files in subfolders of /docker-entrypoint-initdb.d are not run automatically.)

-- PostGIS adds geometry/geography types and spatial functions (ST_Area, ST_AsGeoJSON...).
CREATE EXTENSION IF NOT EXISTS postgis;

-- By default PUBLIC (every role) may connect to every database. Remove that, then
-- grant CONNECT only to this database's own roles. This is what stops the test roles
-- from ever reaching the real warehouse, and the real roles from reaching the test one.
REVOKE CONNECT ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO :"owner_role", :"reader_role";

-- Nobody gets to create objects in "public" by accident.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- The three layers, owned by the owner role so dbt can create and replace tables in them.
CREATE SCHEMA IF NOT EXISTS raw       AUTHORIZATION :"owner_role";
CREATE SCHEMA IF NOT EXISTS modelled  AUTHORIZATION :"owner_role";
CREATE SCHEMA IF NOT EXISTS reporting AUTHORIZATION :"owner_role";

COMMENT ON SCHEMA raw       IS 'Source data exactly as loaded, plus dataset version metadata. Append-only.';
COMMENT ON SCHEMA modelled  IS 'Cleaned, typed, conformed data (GPC sectors, tCO2e, crosswalked cities). Built by dbt.';
COMMENT ON SCHEMA reporting IS 'Aggregates and views served by the API. Built by dbt. The only schema the reader role can read.';

-- Reader: read-only on reporting.
GRANT USAGE ON SCHEMA reporting TO :"reader_role";
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO :"reader_role";

-- dbt drops and recreates tables on every run, so a one-off GRANT would be lost.
-- Default privileges apply to every FUTURE table the owner creates in reporting.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA reporting
  GRANT SELECT ON TABLES TO :"reader_role";
