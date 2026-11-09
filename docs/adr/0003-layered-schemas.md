# ADR 0003: Layered schemas in one database, access enforced by Postgres roles

- **Status:** Accepted; implemented in Stage 1 (`db/init/lib/layers.sql`), recorded in
  Stage 8.
- **Date:** 2026-11-09 (decision taken 2026-11-05)

## Context

The data passes through three stages: source files exactly as published, a cleaned and
conformed model, and the tables the API serves. They have different owners and readers.
The pipeline writes all three. The API must read only the last one, so that a bug or a
compromised API credential can never expose or depend on unvalidated raw data. dbt has to
join across the stages in one query (for example, raw rows to the crosswalk seed).

## Decision

1. **One Postgres database per environment, three schemas:** `raw` (append-only, as
   loaded), `modelled` (dbt staging, seeds, dimensions, facts, snapshots) and `reporting`
   (one contract-enforced table per API endpoint).
2. **Two roles per database.** `pipeline` owns the three schemas. `api_reader` has
   `USAGE` and `SELECT` on `reporting` only. `ALTER DEFAULT PRIVILEGES` keeps that grant
   on tables dbt drops and recreates, and a dbt test checks it after every build
   (`tests/assert_api_reader_can_read_reporting.sql`).
3. **`CONNECT` is revoked from `PUBLIC`** and granted per database, so the roles of
   `warehouse` and `warehouse_test` cannot reach each other's database.
4. **Staging lives in `modelled` with a `stg_` prefix**, not in a fourth schema: the
   pipeline role cannot create schemas, by design.

The same SQL file builds `warehouse` and `warehouse_test`, so the test database has the
same layers and grants as the real one.

## Consequences

- "The API never reads raw" is a database permission, tested in three places (dbt,
  `tests/transform/`, `tests/api/`), not a coding convention.
- Cross-layer joins are ordinary SQL, with no foreign data wrapper or `dblink`.
- All layers share one server's resources and one backup. At this size (2.24M emission
  rows, a 40 s full build) that is not a constraint.

## When we would choose differently

- **Separate databases or servers per layer** if the layers needed different hardware,
  retention or backup policies, or if raw data were large enough that serving traffic
  should never compete with loads.
- **A warehouse with cross-database queries** (BigQuery, Snowflake) would make separate
  projects or databases per layer the natural choice, with the same role design.
- **A fourth `staging` schema** if several teams owned different layers and needed
  separate grants on staging.
