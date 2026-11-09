# ADR 0005: A read-only API over contract-enforced reporting tables

- **Status:** Accepted; reporting implemented in Stage 4, the API in Stage 6. Recorded in
  Stage 8.
- **Date:** 2026-11-09 (decision taken 2026-11-08)

## Context

The API publishes figures that are easy to misread: they describe a satellite-derived
urban centre, not the administrative city (ADR 0001), and their sector labels are
provisional (ADR 0002). The labels, flags and lineage must therefore be on every
response, and they must be the same wherever a figure appears. The API also must not be a
way to change or reach unvalidated data.

## Decision

1. **Reporting is designed backwards from the endpoints:** one dbt table per endpoint,
   with an enforced contract (names, types, `not_null`, primary keys and checks as real
   Postgres constraints). Labels, flags, review statuses and version ids are columns.
2. **The API is a thin read layer.** It runs one `SELECT` per table (`api/queries.py`) and
   never joins, aggregates or calls PostGIS. GeoJSON is precomputed in `city_boundaries`.
3. **Read-only, three ways** (`api/db.py`): the API is given only the reader role's
   credentials, every connection is `default_transaction_read_only` with a 5 s statement
   timeout, and every new connection checks its own privileges and refuses a role that
   can use `raw` or `modelled` or create objects.
4. **Tables, not views:** Postgres enforces constraints only on tables, and dbt swaps a
   rebuilt table in by rename, so the API never sees a half-built one.

## Consequences

- The API cannot drift from the labels in the warehouse: there is no logic in it to drift.
  A test checks that every per-city endpoint carries the urban-centre label, flags and
  versions, and the OpenAPI document is a committed snapshot.
- A new endpoint needs a new reporting model first. That is intended, but slower.
- No authentication or rate limiting is built in. The data is public and read-only; a
  production deployment would add both in a gateway.

## When we would choose differently

- **Views or a semantic layer** if consumers needed ad hoc slicing (for example, any
  sector grouping), with the labels enforced by the semantic layer instead.
- **Logic in the API** if responses depended on the caller (personalisation, access
  rules per row), which tables built ahead of time cannot express.
- **A write API** only with a separate service and role. This one stays read-only.
