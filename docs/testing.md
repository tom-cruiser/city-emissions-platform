# Testing and CI

How tests are isolated from the real warehouse, what they cover, and CI. Back to the [README](../README.md).

## Testing

```bash
uv run pytest -q                    # DB tests skip if Postgres is down
REQUIRE_TEST_DB=1 uv run pytest -q  # CI: an unreachable test DB is a failure
```

Tests can never touch the real warehouse. There are three independent layers:

1. **Credentials.** Tests connect as `test_pipeline`. `db/init/lib/layers.sql` revokes
   `CONNECT` from `PUBLIC` on each database and grants it only to that database's own
   roles, so `test_pipeline` → `warehouse` fails with *permission denied for database*.
   `tests/test_db_isolation.py` asserts exactly that.
2. **Name guard.** The session refuses to start unless `TEST_POSTGRES_DB` ends in `_test`,
   and the fixture re-checks the connected database name.
3. **Settings override.** For the whole session, `PIPELINE_*` and `POSTGRES_DB` point at
   the test values, so code under test that builds its own connection also lands on
   `warehouse_test`.

Each DB test also runs inside `conn.transaction(force_rollback=True)`, and first
truncates `raw` inside it. `warehouse_test` keeps a committed sample load for dbt; each
test still starts from an empty `raw`, and the rollback restores the sample. The pipeline's own
per-file transactions nest inside it as savepoints, so nothing a test writes is ever
committed. (An earlier version of the fixture lacked this and committed for real. On an
idle connection, psycopg's `conn.transaction()` *is* the outermost transaction.)

`tests/transform/` covers the dbt project. Run it **after** `scripts/dbt-build.sh test`:

- `test_reporting_access.py` connects as `test_api_reader`, the way the API will, and
  reads every reporting table (non-empty), and is refused on `raw` and `modelled`.
  Without a build, `reporting` is empty and the test skips (fails under `REQUIRE_TEST_DB=1`).
- `test_reporting_manifest.py` parses the project in-process (no database) and fails if
  a reporting model is not a table with an enforced contract and typed columns, or if a
  `*_version_id` column is not tied to `dataset_versions` and to the *current* version.
  Models that hold older versions by design are listed there and must *not* use the
  current-version test.

`tests/api/` covers the API, against `warehouse_test` as `test_api_reader`, after a sample
load and `scripts/dbt-build.sh test` (skips otherwise; fails under `REQUIRE_TEST_DB=1`):

- **Isolation** (`test_db_isolation.py`, through the API's own engine): connects as the
  reader, session is read-only, `raw` and `modelled` are denied, writes are refused, the
  pipeline role's credentials are refused (fails closed), and no API SQL names `raw.` or
  `modelled.`.
- **Labels and lineage** (`test_endpoints.py`): every per-city endpoint, for a flagged and an
  unflagged city, carries `territory_basis`, flags, review status and versions, and every
  version id resolves at `/v1/datasets/{id}` as current.
- **Values** equal the reporting tables; **known data**: 25 cities, Accra's four flags,
  revisions 5 changed + Dakar 192 removed / 192 added, 3 EDGAR versions with one current.
- **Pagination** (pages join up to the full list, stable order), **filters**, **404s** on
  every city endpoint, **422s** for 16 kinds of bad input, **503** with the database down.
- **Enums** equal the values in reporting (`test_enums.py`).
- **OpenAPI** (`test_openapi.py`): the caveat leads the description and is on every
  emissions field, and the document equals the committed `docs/openapi.json`. After an
  intended API change: `UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/api/test_openapi.py`
  and commit the snapshot with the change.

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request to `main` (and by hand).
Changes go to `main` through pull requests. The **`test`** and **`api-image`** jobs are
required checks; `orchestration-image` can be made one too.

| Job | Steps |
|---|---|
| `test` | `uv sync --locked` (Python 3.12, uv cache keyed on `uv.lock`) → `ruff` → `docker compose up -d --wait db` → sample load into `warehouse_test` → `dbt compile --target warehouse` → `dagster definitions validate` → `scripts/dbt-build.sh test` → `pytest` (includes Dagster's job runs on the sample) → `git diff --exit-code` |
| `api-image` | builds `api/Dockerfile` with the BuildKit cache; never pushed |
| `orchestration-image` | builds `orchestration/Dockerfile` (`GIT_COMMIT` = `github.sha`); never pushed |

- **Same database as local.** CI copies `.env.example` to `.env` and starts the database
  with Docker Compose: same PostGIS image, same `db/init` scripts, same healthcheck. (A
  GitHub `services:` container starts before checkout and could not run `db/init`.)
- **Nothing skips.** `REQUIRE_TEST_DB=1` makes an unreachable database or an unbuilt
  `reporting` a failure.
- **`GIT_COMMIT` is `github.sha`**, passed through `scripts/dbt-build.sh` to the snapshots.
- **The warehouse code paths compile.** The test target never runs `raw_origins`'s
  `download` branch or the `origin = 'download'` test. `dbt compile --target warehouse`
  against the empty `warehouse` renders them.
- **The API contract is enforced.** The OpenAPI snapshot test runs in `pytest`, refuses
  `UPDATE_OPENAPI_SNAPSHOT` when `CI` is set, and the final `git diff --exit-code` fails if
  the run changed any tracked file.
- **Pinned actions.** Every action is pinned to a commit SHA. Dependabot proposes updates
  weekly (`.github/dependabot.yml`, GitHub Actions only). `tests/test_ci_workflow.py`
  checks the triggers, `REQUIRE_TEST_DB`, `GIT_COMMIT`, the step order, the pins and that
  no image is ever pushed.

**Duration.** Expect ~2–3 minutes with a warm uv cache. A dry run of the same steps on a
fresh database locally took 58 s: database up 7 s, load 1 s, warehouse compile 12 s, dbt
build 17 s, pytest 21 s. CI adds checkout, `uv sync` and the PostGIS image pull.

**Finding a failure fast.** Lint runs first and fails in seconds, with ruff findings as
annotations on the PR's changed lines. On any failure, the run's **summary page** lists the
failed pytest tests and dbt nodes with their messages (`scripts/ci_failure_summary.py`).
The `failure-details` artifact (7 days) holds `pytest.xml`, `run_results.json`, `dbt.log`
and the database log. From a terminal: `gh pr checks --watch`, then
`gh run view --log-failed`.
