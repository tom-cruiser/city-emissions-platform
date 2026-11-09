# Orchestration (Dagster)

Assets, schedule, checks and failure handling. Back to the [README](../README.md).

## Orchestration (Dagster)

Dagster runs the whole pipeline as one asset graph, from the source files to the reporting
tables:

```
source/edgar_ucdb ──► raw/edgar_ucdb_emissions ──┬──► raw/ghs_ucdb_urban_centres ◄── source/ghs_ucdb
source/geoboundaries ──► raw/geoboundaries_features
                         (all three) ──► staging ──► modelled (+ seeds, snapshots) ──► reporting/* (7 tables)
```

- **Sources:** three assets, one per raw table. Each is a thin wrapper around the same
  `ingestion.pipeline` function the CLI calls (`run_download`, or `run_sample` with config
  `mode: sample`). It records per-file results as metadata. The asset keys equal the dbt
  source names, so dagster-dbt links them to staging with no mapping code.
  - GHS-UCDB depends on EDGAR: its ID check compares with the EDGAR version already in raw.
  - The source files are external assets with their URL and licence.
- **dbt:** every seed, model and snapshot is an asset (`reporting/cities`,
  `modelled/snap_city_crosswalk`, …). The run is a single `dbt build`, and dbt tests show as
  asset checks.
  - Singular tests that read several models are logged as observations, not checks:
    dagster-dbt can't attach them to one asset.
  - `GIT_COMMIT` comes from `scripts/git-commit.sh`, as for `scripts/dbt-build.sh`. The
    image has no `.git`, so build it with `GIT_COMMIT=$(scripts/git-commit.sh)`.
- **`PIPELINE_TARGET`** (`warehouse` | `test`) picks the database for ingestion and dbt
  together, so they can't drift apart.
  - Download mode is refused on `test`, so tests and CI never touch the network.
  - The sample is refused anywhere but a `*_test` database, as everywhere else.

### Run it

```bash
# Existing volume (created before Stage 5)? Create Dagster's storage database once:
docker compose up -d db && docker compose exec db bash /docker-entrypoint-initdb.d/03-dagster-db.sh

GIT_COMMIT=$(scripts/git-commit.sh) docker compose build dagster-webserver dagster-daemon
docker compose up -d --wait dagster-webserver dagster-daemon
```

Open **http://127.0.0.1:3030**: Lineage shows the graph, and *Materialize all* runs it.
Set `DAGSTER_PORT` in `.env` to change the port; 3000 is often taken by web dev servers.
The UI can start runs and has no login, so it is bound to 127.0.0.1 only: never publish it.

- **Without Docker:** `scripts/dagster-dev.sh` runs `dagster dev` on the host against the
  Compose database (`PIPELINE_TARGET=test scripts/dagster-dev.sh` for warehouse_test).
- **The containers:**
  - They get only the pipeline role and Dagster's own storage role, never the API reader
    or the superuser.
  - Downloads go to the `raw-downloads` volume, not the host's `data/raw/`.

### Storage

Dagster keeps its runs, schedules and event logs in its own **`dagster` database** on the
same Postgres server (`orchestration/dagster.yaml`), never in the warehouse.
`db/init/03-dagster-db.sh` creates it, and it is safe to re-run:
- The `dagster` role owns it and can't connect to `warehouse` or `warehouse_test`.
- The warehouse roles can't connect to it.

`tests/orchestration/test_storage_db.py` checks both directions.

### Schedule

`weekly_refresh_schedule` runs every asset on Mondays at 03:00 UTC. **It is off by
default**, so cloning the repo and starting Dagster never downloads anything unasked. To
turn it on, use the UI (*Automation* → `weekly_refresh_schedule` → on), or run:

```bash
docker compose exec dagster-daemon dagster schedule start weekly_refresh_schedule -m orchestration.definitions
```

A production deployment would turn it on.
- **Why weekly:** to notice failures early (a moved URL, a broken file, a server change).
  The sources don't change weekly: EDGAR is released about once a year.
- **Cost:** most weeks every file is skipped by SHA-256 and dbt rebuilds identical tables.
  Each run still re-downloads about 375 MB, since downloads aren't cached.

### Checks

- **`load_check_warnings`** on each raw asset: WARN (never blocking) if the current
  version(s) of that source have a `warn` row in `raw.load_checks`. On the real warehouse,
  GHS-UCDB warns (`geometry_valid`, `id_match_edgar`; see [Load checks](ingestion.md#load-checks)).
- **Freshness** of the 7 reporting tables: each must have been rebuilt by Dagster within
  **8 days**. It is a `FreshnessPolicy` (Dagster 1.13's replacement for freshness checks),
  evaluated by the daemon.
  - **The window is tied to the weekly schedule:** 7 days plus a day of slack. If the
    schedule changes, change `REPORTING_FRESHNESS` in `orchestration/dbt.py` with it.
  - It turns red when the schedule is off or every run for a week has failed. With the
    schedule off by default, expect it red until you turn it on.
  - Builds by `scripts/dbt-build.sh` are invisible to it.
- **dbt tests** as asset checks, including the 2 known warnings (Accra, Buenos Aires).

### When a source fails

| Failure | Shown as | What happens downstream |
|---|---|---|
| One of the 24 geoBoundaries files fails (e.g. HTTP 404) | `raw/geoboundaries_features` red. Its metadata lists every file; the error names the failing one | The other 23 are **committed** (one transaction per file). **dbt does not run** in that run |
| EDGAR or GHS-UCDB download fails | Retried twice, a minute apart, then red | EDGAR failing skips GHS-UCDB (it depends on EDGAR). geoBoundaries still loads. dbt does not run |
| GHS-UCDB load check fails (`LoadCheckError`) | Red, with the check's message | dbt does not run |
| A dbt test errors | That check red | dbt skips the nodes downstream of it; other branches build |
| A load-check warning | Yellow check on the raw asset | Nothing is blocked |

Users are never affected: raw is append-only and `reporting` is rebuilt only by a run that
gets to dbt, so the API keeps serving the last good build.
- **Recovery:** fix the cause, then re-materialize the failed asset and everything
  downstream in the UI, or wait for the next scheduled run. Files already loaded are
  skipped.
- **Alerting:** none yet (see Next steps).
- **Concurrency:** one run at a time (`max_concurrent_runs: 1`), so two loads never race.

### Tests

`tests/orchestration/`:
- **Definitions:** they load, and every `raw/*` key is an ingestion asset (a renamed
  table would otherwise silently cut lineage).
- **Lineage:** every reporting table traces back to a source file.
- **Configuration:** the schedule is off, the freshness policy is set on reporting only,
  and the check SQL reads current versions only.
- **Job runs:** the weekly job runs end to end on the offline sample, in process. One
  failed geoBoundaries file fails its asset while the other sources load, and dbt never
  starts.

CI also runs `dagster definitions validate` and builds the Dagster image (no push).
