# Build history

What each stage delivered, as recorded while it was built. Back to the [README](../README.md).

## Build status

| Stage | Scope | Status |
|---|---|---|
| 1 | Repo structure, Docker Compose, PostGIS, schemas and roles | ✅ Done |
| 2 | Source verification, Python ingestion into `raw`, dataset versioning, load checks | ✅ Done |
| 3 | dbt: modelled layer, seeds, tests | ✅ Done |
| 4 | Reporting layer and dbt snapshots | ✅ Done |
| 5 | Dagster orchestration | ✅ Done |
| 6 | FastAPI service and tests | ✅ Done |
| 7 | GitHub Actions CI | ✅ Done |
| 8 | Full docs, diagrams, ADRs | ⏳ Planned |

**Stage 2 items**

1. ✅ **Synthetic EDGAR fixture.** Real EDGAR rows are deliberately *not* committed (see
   [licences](data-sources.md#data-sources--licences)). The offline sample uses a synthetic file with
   EDGAR's exact structure and invented values. See [Synthetic EDGAR fixture](ingestion.md#synthetic-edgar-fixture).
2. ✅ **Separate `warehouse_test` database.** Tests run only against `warehouse_test`,
   whose roles cannot connect to `warehouse`. See [Testing](testing.md#testing).
3. ✅ **GHS-UCDB urban-centre polygons.** The polygons EDGAR's emissions are computed on
   are loaded into `raw` with load checks. See [GHS-UCDB urban centres](ingestion.md#ghs-ucdb-urban-centres).
   The overlap with administrative boundaries is *not* computed here: it belongs to dbt
   (Stage 3), as decided in [ADR 0001](adr/0001-urban-centre-overlap.md).

**Stage 3 items**

1. ✅ **dbt project** in `transform/`: seeds, 5 staging and 4 modelled models, 79 tests. See
   [Modelled layer (dbt)](transform.md#modelled-layer-dbt).
2. ✅ **Overlap model** `city_territory_overlap` (ADR 0001): ratios in Mollweide, km² geodesic,
   `low_urban_overlap` at `var('min_urban_overlap')` = 0.5, warn test at 0.01 for suspected
   crosswalk errors.
3. ✅ **Provisional EDGAR → GPC sector mapping**, [ADR 0002](adr/0002-edgar-to-gpc-sector-mapping.md),
   pending specialist review. Sectors are called *GPC-aligned*, never a *GPC inventory*.
4. ✅ **Guard**: sample/synthetic data is refused by any database not named `*_test`, in
   ingestion and in dbt.

**Stage 4 items**

1. ✅ **Reporting layer**: 7 models in `reporting`, designed backwards from the API
   endpoints, each a table with an enforced dbt contract. Every emissions figure is labelled
   as the emissions of the city's *urban centre* and carries its overlap, flags, review
   status and dataset versions. `api_reader` is tested to read every one after a rebuild.
   See [Reporting layer (dbt)](transform.md#reporting-layer-dbt).
2. ✅ **Snapshots** of the crosswalk and the sector map, both edited in place, with a
   `pg_dump` backup because they cannot be rebuilt. See [Snapshots](transform.md#snapshots).
3. ✅ **Revisions** between EDGAR versions, modelled by comparing dataset versions
   (`city_emission_revisions`). Tested on `warehouse_test` with three synthetic EDGAR
   versions that produce `changed`, `removed` and `added` cells; empty on the real
   warehouse until a second EDGAR version exists.
   See [Revisions between EDGAR versions](transform.md#revisions-between-edgar-versions).
4. ✅ **One build command**, `scripts/dbt-build.sh`, which sets `GIT_COMMIT` from git for
   the snapshots. Local runs and CI call it; Dagster runs dbt through dagster-dbt with
   the same `GIT_COMMIT` rule (`scripts/git-commit.sh`).

**Stage 6 items** (built before Stage 5, since reporting was designed from the endpoints)

1. ✅ **Read-only FastAPI service** over `reporting`: 9 data endpoints plus health and
   readiness. Every response carries the urban-centre label, flags, review statuses and
   dataset versions. See [API (FastAPI)](api.md#api-fastapi).
2. ✅ **Reader role only**, enforced three ways, and tested through the API's own engine.
3. ✅ **Tests** against `warehouse_test` and an OpenAPI snapshot (`docs/openapi.json`).
4. ✅ **Docker Compose service** `api`: only the `api` dependency group, non-root,
   read-only filesystem, reader credentials only, on `127.0.0.1:8000`.
