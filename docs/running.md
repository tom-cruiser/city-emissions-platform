# Running the platform

Full setup, real-data loads and database housekeeping. Back to the [README](../README.md).

## Quick start

Requires Docker and [uv](https://docs.astral.sh/uv/) (uv installs Python 3.12 itself).

```bash
cp .env.example .env                 # then change the passwords
docker compose up -d --wait          # PostGIS on 127.0.0.1:5434 + the API on 127.0.0.1:8000
uv sync                              # Python 3.12 environment from uv.lock (all dependency groups)

# Real data -> warehouse (~25 MB EDGAR, ~70 MB boundaries, 277 MB GHS-UCDB), then build it.
uv run python -m ingestion load --mode download
scripts/dbt-build.sh                 # dbt always runs through this script (sets GIT_COMMIT, reads .env)

# Offline sample -> warehouse_test, build it, then the tests (in this order).
uv run python -m ingestion load --mode sample --target test   # 3 synthetic EDGAR versions + real extracts
scripts/dbt-build.sh test
uv run pytest -q                     # runs against warehouse_test only

scripts/dbt-build.sh test --select cities+   # extra arguments go to dbt build
```

Then open the API docs at **http://127.0.0.1:8000/docs** (Swagger UI) or
**http://127.0.0.1:8000/redoc**. `curl http://127.0.0.1:8000/ready` says whether
`reporting` is built. Before the first `scripts/dbt-build.sh`, it answers 503, while
`/health` (the container's healthcheck) is already up.

`scripts/dbt-build.sh` is the only supported way to run `dbt build` by hand; CI (Stage 7)
calls it too. Dagster (Stage 5) runs `dbt build` through dagster-dbt, so each node becomes
an asset. Both get `GIT_COMMIT` from `scripts/git-commit.sh`: the HEAD commit, with
`-dirty` when tracked files have uncommitted changes, unless `GIT_COMMIT` is already set
(CI, Docker images without `.git`). It passes `.env` to dbt when present, and profiles.yml
holds no secrets. Other dbt commands (`parse`, `test`, `docs`) can still be run directly with
`uv run --env-file .env dbt <command> --project-dir transform --profiles-dir transform`.

A full `dbt build` on the real warehouse takes about 40 s (2.24M emission rows).

Re-running a load is safe: a file whose SHA-256 is already recorded is skipped.

> **Sample mode loads synthetic emissions, so it only loads into `warehouse_test`.** Any
> emissions number it produces is invented. Sample and synthetic data are refused by any
> database whose name does not end in `_test`: `load --mode sample` without
> `--target test` exits with an error before writing anything. The check runs on the
> database the connection actually reached, at the start of the sample run and again in
> `register_version`, which every loader goes through (`tests/ingestion/test_test_db_guard.py`).
> It exists because on 2026-11-07 a sample load reached the real warehouse by mistake;
> that was removed with [`db/corrections/2026-11-07_remove_sample_versions_from_warehouse.sql`](../db/corrections/2026-11-07_remove_sample_versions_from_warehouse.sql).

**Created your volume before `warehouse_test` existed?** The init scripts only run on an
empty volume. Add it without losing data:

```bash
docker compose up -d --wait   # recreate the container so it sees the TEST_* variables
docker compose exec db bash /docker-entrypoint-initdb.d/02-test-db.sh   # idempotent
```

Inspect what was loaded:

```bash
docker compose exec db psql -U climate -d warehouse -c \
  "SELECT dataset_version_id, source_name, source_key, origin, row_count, left(file_sha256,12), loaded_at
   FROM raw.dataset_versions ORDER BY 1"
```

`docker compose down -v` deletes the database volume. The init scripts in `db/init/`
only run against an empty volume.

> ⚠️ **Back up the snapshots before `docker compose down -v`.** Everything else in the
> database can be rebuilt (ingestion from the source files, dbt from `raw`), but the dbt
> snapshot tables hold history that exists nowhere else. Run the backup command in
> [Snapshots](transform.md#snapshots) first.
