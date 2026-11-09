# API (FastAPI)

Endpoints, labels, errors and the read-only guarantees. Back to the [README](../README.md).

## API (FastAPI)

A read-only HTTP API over `reporting` (`api/`). Each endpoint reads one reporting table
built for it by dbt; the API never joins, aggregates or calls PostGIS (`api/queries.py`).

| Endpoint | Query parameters | Returns |
|---|---|---|
| `GET /v1/cities` | `country` (ISO3, repeatable), `review_status`, `flag` (repeatable, all must be set), `limit`, `offset` | page of cities with flags, review status, versions, latest urban-centre GHG |
| `GET /v1/cities/{city_id}` | | one city |
| `GET /v1/cities/{city_id}/emissions` | `pollutant` (one; default `GHG`), `sector` (repeatable), `year_from`, `year_to`, `limit`, `offset` | urban-centre emissions by EDGAR sector and year, GPC-aligned labels per row |
| `GET /v1/cities/{city_id}/trend` | `pollutant`, `year_from`, `year_to` | per year, all sectors, with `prev_year` and annualised change |
| `GET /v1/cities/{city_id}/revisions` | `revision_type`, `pollutant`, `limit`, `offset` | changes between consecutive EDGAR versions |
| `GET /v1/cities/{city_id}/overlap` | | overlap metrics, thresholds used, match note |
| `GET /v1/cities/{city_id}/boundary` | | GeoJSON `FeatureCollection` (`application/geo+json`): boundary + urban centre, bbox, licences |
| `GET /v1/datasets`, `GET /v1/datasets/{id}` | `source_name`, `is_current`, `limit`, `offset` | lineage: source URL, SHA-256, licence, load warnings |
| `GET /health`, `GET /ready` | | liveness (no database) / readiness (database answers, reporting built) |

**Labels and lineage in every response.** Every city-scoped response has a `city` block:
`territory_basis` (always `ghs_urban_centre`), `uc_share_inside_admin`, the four flags and a
`flags` list, `crosswalk_review_status`, and `versions` (EDGAR, GHS-UCDB, geoBoundaries
dataset version ids, each resolvable at `/v1/datasets/{id}`). Every emissions value is named
`urban_centre_emissions`. Emission rows add `mapping_quality` and
`sector_mapping_review_status`. `/v1/datasets` is the lineage itself and has no figures.

**One pollutant per emissions request.** GHG already contains CO2, so the API never returns a
list that invites adding pollutants together. Sectors are never summed into GPC totals.

**Pagination, filters and errors.** List endpoints take `limit` (1–100, default 50) and
`offset`, and return `total`; order is always the table's key, so pages are stable. Filters
are enums (`pollutant`, `sector`, `review_status`, `flag`, `revision_type`, `source_name`).

| Case | Status | Body |
|---|---|---|
| Unknown city / dataset version | 404 | `{"detail": "city 'x' not found", "code": "city_not_found"}` |
| Malformed `city_id`, unknown enum value, `limit` outside 1–100, `offset` < 0, `year_from` > `year_to` | 422 | FastAPI's standard validation body |
| Database unreachable or a statement over 5 s | 503 | `{"code": "database_unavailable"}` |
| The API was given a role that can do more than read `reporting` | 500 | `{"code": "unsafe_database_role"}` |

**Numbers.** Emissions are JSON numbers (IEEE-754 doubles, ~15 significant digits). The
warehouse stores them as exact `numeric`; the API converts only when serialising, and says
so in its OpenAPI description.

**Read-only, three ways** (`api/db.py`):

1. Its settings hold only the reader role's credentials (`API_READER_*`). The API never
   receives the pipeline password.
2. Every connection sets `default_transaction_read_only=on` and a 5 s `statement_timeout`.
3. Every new connection checks its own privileges and is refused if the role can use `raw`
   or `modelled` or create objects. Given the wrong credentials, the API fails closed.

Each per-city request reads its tables in one `REPEATABLE READ` transaction, so the `city`
block and the rows come from the same snapshot.

**Running it.** In Docker Compose (the `api` service, started by `docker compose up -d --wait`):

```bash
docker compose up -d --wait           # db + api; api waits for the db healthcheck
open http://127.0.0.1:8000/docs       # or xdg-open / paste into a browser
curl -s http://127.0.0.1:8000/v1/cities/jakarta-idn | python -m json.tool
docker compose build api              # after changing api/ or the api dependency group
docker compose logs -f api
```

The image (`api/Dockerfile`) installs only the `api` dependency group from `uv.lock`, runs
uvicorn as a non-root user, and in Compose has a read-only filesystem, no Linux
capabilities, and `127.0.0.1` only (`API_PORT`, default 8000). It is given exactly five
variables: database host, port and name, and the reader's user and password
(`tests/test_compose.py` fails if a pipeline or superuser variable is added).

Without Docker, against the warehouse in `.env`:

```bash
uv run uvicorn --factory api.main:create_app --port 8000 --reload
```
