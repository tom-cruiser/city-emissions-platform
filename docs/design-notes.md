# Design notes

Every design decision and known limitation in full, as recorded while building. The README summarises them; the major decisions have [ADRs](adr/). Back to the [README](../README.md).

## Design decisions (so far)

- **Schemas, not separate databases, for layers.** dbt has to join across layers, and
  Postgres cannot join across databases without extensions.
- **Least-privilege roles enforced in the database**, not by convention.
- **Raw rows as JSONB.** A new year column upstream does not break the load, and raw
  stays exactly as published.
- **Content-hash dataset versions.** The SHA-256 *is* the version, which gives
  idempotency and lineage from one mechanism.
- **Admin boundaries plus a reviewed crosswalk, joined by ID.** Cities report emissions
  for their administrative territory, and names are too unreliable to join on.
- **Synthetic, not real, EDGAR rows in the repo.** It respects the ND licence term while
  still testing the real loader, file format and known data-quality problems offline.
- **A separate test database with its own roles**, so isolation is enforced by
  Postgres permissions rather than by careful configuration.
- **GeoPackage read without GDAL.** The format is SQLite plus a small documented header.
  Parsing it in 125 lines avoids a heavy native dependency in the pipeline image, and every
  load cross-checks the parsed header against PostGIS.
- **Load checks stored next to the data** (`raw.load_checks`), so a warning such as
  "22 invalid polygons" is queryable lineage, not a log line that scrolls away.
- **Staging inside `modelled`, not a fourth schema.** The pipeline role cannot create
  schemas, and a `stg_` prefix keeps them apart.
- **No dbt packages.** Four small generic tests in `transform/tests/generic/` instead of
  `dbt_utils`, so CI needs no `dbt deps` (network) step.
- **Reporting designed backwards from the API**, one table per endpoint, contract-enforced,
  so the API is a thin read layer with no joins or PostGIS calls of its own.
- **Methodology in seeds and vars, not SQL.** The sector mapping, crosswalk and thresholds
  can be reviewed and changed without touching model code.
- **Dependencies split by where they run** (`pyproject.toml`): a small shared base
  (pydantic, psycopg), `api` (FastAPI, uvicorn, SQLAlchemy Core), `pipeline` (dbt,
  ingestion libraries), `orchestration` (Dagster) and `dev` (all of them plus pytest and
  ruff, the default for `uv sync`). The API image installs only `api`: 24 packages on Linux, no dbt
  or Dagster. The Dagster image installs `pipeline` and `orchestration`, not `api`.
- **Python 3.12 only.** dagster-dbt 0.29.28 declares `requires_python <3.14`. uv
  ignores that cap and would install on 3.14, but pip correctly refuses, so 3.14 is
  unsupported here. 3.11–3.13 all install and import cleanly.

## Known limitations

- **Urban centre ≠ city boundary.** EDGAR measures a satellite-derived urban centre,
  while boundaries are administrative. Extents can differ greatly; Jakarta's urban
  centre (123 Mt CO2e) extends well beyond DKI Jakarta. `city_territory_overlap` measures
  this: 12 of 25 cities have less than half their urban centre inside the boundary. Never
  read an emissions figure as "emissions inside this boundary".
- **EDGAR v2024 was built on an earlier GHS-UCDB release than the polygons loaded.**
  EDGAR uses 11,686 urban-centre IDs; GHS-UCDB V1.2 (loaded here) has 11,422. For the 25
  crosswalk cities the IDs, names and countries match, but **the shapes are not verified
  identical** to those EDGAR computed emissions on. Checking would need the older
  release (another 277 MB). Overlap figures therefore describe the V1.2 polygon, which
  may differ from EDGAR's territory.
- **Official areas are mostly secondary sources.** `official_area_km2` is the Ghana
  Statistical Service figure for Accra, the city government's for Buenos Aires, and
  Wikipedia infobox figures for the other 23. That is enough for the 25% sanity check it
  feeds; it is not an authoritative area.
- **Sector labels are GPC-aligned, not a GPC inventory**: scope 1 only, urban-centre
  territory, modelled top-down, provisional mapping. See [ADR 0002](adr/0002-edgar-to-gpc-sector-mapping.md).
- **Downloads are not cached.** `load --mode download` re-fetches every file, including
  the 277 MB GHS-UCDB zip (25 min on the JRC server on 2026-11-06, 90 s on 2026-11-07);
  identical bytes are then skipped at load (`skipped (already loaded)`, with the
  matching version id).
- **London is excluded:** no single geoBoundaries unit for Greater London at ADM2.
- **No migrations tool yet.** The raw DDL is `CREATE TABLE IF NOT EXISTS`, so changing an
  existing table needs a manual `ALTER` (or recreating the volume). Example: widening the
  `origin` check to include `synthetic` on an existing database:
  ```sql
  ALTER TABLE raw.dataset_versions DROP CONSTRAINT dataset_versions_origin_check;
  ALTER TABLE raw.dataset_versions ADD CONSTRAINT dataset_versions_origin_check
    CHECK (origin IN ('download', 'sample', 'synthetic'));
  ```
- **Offline runs show invented emissions.** The synthetic fixture is for testing only.
- **No authentication or rate limiting on the API.** The data is public and the API is
  read-only, so neither is built in. A production deployment would put API keys and rate
  limits in a gateway in front of it (not in the app), along with TLS.
