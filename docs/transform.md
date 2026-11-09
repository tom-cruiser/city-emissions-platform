# dbt: modelled and reporting layers

Models, tests, revisions and snapshots. Back to the [README](../README.md).

## Modelled layer (dbt)

All models live in the `modelled` schema. The `pipeline` role owns the three layer
schemas and cannot create others, so staging models share it, prefixed `stg_`. Every row
carries the `dataset_version_id` of the raw file it came from.

| Model | Grain (one row is…) | Built as | Why |
|---|---|---|---|
| seeds `city_crosswalk`, `edgar_sector_map`, `edgar_pollutants` | a city / EDGAR sector / pollutant | table | seeds |
| `stg_raw__current_versions` | a source file: its current version | view | tiny, must reflect raw |
| `stg_edgar__urban_centres` | an EDGAR urban centre, names repaired | view | 11.7k rows, cheap |
| `stg_edgar__emissions` | urban centre × emission column, unpivoted from JSON | view | read once, by the fact table |
| `stg_ghs_ucdb__urban_centres` | an urban-centre polygon, repaired, SRID 54009 | table + GiST | repairing 11k polygons is the slow step; read by tests and overlap |
| `stg_geoboundaries__boundaries` | a boundary polygon, repaired, SRID 4326 | table + GiST | parsing and repairing ~6.7k features |
| `dim_city` | a crosswalk city | table | carries the boundary geometry |
| `fct_urban_centre_emissions` | urban centre × pollutant × EDGAR sector × year, **current EDGAR version only** (2.24M rows) | table | source-quality tests cover every urban centre |
| `fct_city_emissions` | city × pollutant × EDGAR sector × year, **current EDGAR version only** (4,800 rows) | table | what later stages read |
| `stg_raw__dataset_versions`, `stg_raw__load_checks` | every allowed dataset version (with `is_current`) / its load checks | view | lineage for reporting and revisions |
| `stg_edgar__crosswalk_emissions_by_version` | crosswalk urban centre × emission column × **every** EDGAR version | view | same unpivot macro, filtered to the 25 cities first |
| `fct_city_emissions_by_version` | city × EDGAR version × pollutant × sector × year | table | input to `city_emission_revisions`; its current slice must equal `fct_city_emissions` |
| `city_territory_overlap` | a crosswalk city | table | geometry operations |

Nothing is incremental: a full rebuild takes ~40 s. History comes from dataset versions
(sources) and dbt snapshots (seeds edited in place): see [Snapshots](#snapshots).

**Which raw version is modelled.** `stg_raw__current_versions` picks, per source file,
the most recently loaded version among the allowed origins: `download` on the warehouse,
`sample`/`synthetic` on the test target. Asking for sample or synthetic data on a
database not named `*_test` is a compile error (`macros/raw_origins.sql`), mirroring the
ingestion guard.

**Units.** EDGAR's declared unit must be `ton/year`, or the build fails. Values stay in
tonnes per year as published. `unit` comes from the pollutant seed: `t CO2e/yr` (GHG,
GWP100 AR5), `t CO2/yr`, `t/yr` (NOx, PM2.5). Pollutants are never added together:
GHG already contains CO2 (`is_ghg_total`). EDGAR has 8 years (1975, 1990, 2000, 2005,
2010, 2015, 2020, 2022), and nothing interpolates between them.

**Encoding.** EDGAR's names are UTF-8 bytes decoded as Windows-1252. `repair_mojibake`
maps each character back to its byte and decodes as UTF-8. That fixes all 608 distinct
mis-encoded strings, including the five bytes Windows-1252 leaves undefined (`Ã\u0081vila` →
`Ávila`). A correctly encoded name would make the build fail on purpose: it would mean
EDGAR fixed its encoding and the repair must be revisited.

**Sectors.** `edgar_sector_map` adds a GPC sector and `mapping_quality` (`approximate` or
`mixed`; nothing is `direct` today) next to the EDGAR sector, which stays the primary
label. Provisional, pending specialist review: [ADR 0002](adr/0002-edgar-to-gpc-sector-mapping.md).

**Geometry.** Staging applies `ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))` and
keeps a `geom_was_valid` flag (22 urban centres repaired, 0 boundaries). Raw is never
modified. A test checks that repair keeps every row.

**Crosswalk.** Joined by ID only. `review_status` and `match_note` are carried into
`dim_city`. `dim_city` compares the geodesic boundary area with `official_area_km2`
and warns beyond `var('admin_area_tolerance')` (25%). 23 cities are within 13%; Accra
(−72%) and Buenos Aires (+374%) warn, as expected.

**Overlap** (`city_territory_overlap`, computed in `macros/overlap_metrics.sql`):

| Column | Meaning |
|---|---|
| `uc_share_inside_admin` | area(urban centre ∩ boundary) / area(urban centre), Mollweide. **Flag basis** |
| `admin_share_covered`, `iou` | information only, Mollweide |
| `uc_area_km2`, `admin_area_km2`, `intersection_area_km2` | geodesic (`geography`) |
| `low_urban_overlap` | share < `var('min_urban_overlap')` (0.5): the figure describes a substantially different territory |
| `suspected_crosswalk_error` | share < `var('suspect_crosswalk_overlap')` (0.01): the match itself is suspect; warn test |
| `min_urban_overlap`, `suspect_crosswalk_overlap` | the thresholds used, recorded per row |

On the real data: 12 of 25 cities have `low_urban_overlap`. Only Accra (0.005) has
`suspected_crosswalk_error`. Paris (0.074) is low but correct: département 75 is the
city, and its urban centre is 13× larger.

**Tests** (94 on seeds, staging and modelled models; 187 in the whole project). Error severity covers: grain uniqueness, row counts against
sources, complete series per urban centre and per city (this catches double counting such
as the synthetic duplicate Lagos), exactly one EDGAR version in each fact table, GHG ≥ CO2,
no negatives, an unknown pollutant or sector, `ton/year`, geometry validity/SRID, shapes
renamed upstream, lossy names on crosswalk cities, ratios in [0, 1], and Mollweide vs
geodesic share < 1e-4. Two singular tests run macros on fixed cases: names from EDGAR for
`repair_mojibake`, and squares with known answers for `overlap_metrics`. **Warn** severity
is for data findings, not broken builds: boundary area vs official (Accra, Buenos Aires)
and the 0.01 overlap (Accra). These keep warning until the crosswalk is fixed.

## Reporting layer (dbt)

The `reporting` schema is the API's whole world: `api_reader` can read nothing else. Each
model was designed from the endpoint that will serve it (Stage 6).

| Model | Endpoint | Grain (one row is…) | Rows |
|---|---|---|---|
| `cities` | `GET /cities` | a crosswalk city: match, flags, years, latest urban-centre GHG | 25 |
| `city_emissions` | `GET /cities/{id}/emissions` | city × pollutant × **EDGAR sector** × year | 4,800 |
| `city_emissions_trend` | `GET /cities/{id}/trend` | city × pollutant × year, sectors summed | 800 |
| `city_boundaries` | `GET /cities/{id}/boundary` | a city: boundary + urban centre as GeoJSON, bbox, licences | 25 |
| `city_overlap` | `GET /cities/{id}/overlap` | a city: overlap metrics, flags, thresholds used | 25 |
| `dataset_versions` | `GET /datasets` | a dataset version (current or not), with its load-check warnings | 26 |
| `city_emission_revisions` | `GET /cities/{id}/revisions` | city × pollutant × sector × year × consecutive EDGAR version pair, changed cells only | 0 (one EDGAR version) |

**Every model is a table with an enforced contract** (`dbt_project.yml`). Column names and
types are declared in `models/reporting/_reporting.yml`, and `not_null` / primary-key /
check constraints are real Postgres constraints, so a wrong type or a null fails the build
instead of reaching the API. Tables, not views: Postgres only enforces constraints on
tables, dbt swaps a rebuilt table in by rename (the API sees the old or the new table,
never a half-built one), and the geometry work runs once per build. Descriptions are
persisted as Postgres `COMMENT`s, so the labels below are visible in the database itself.

**What travels with every figure.** EDGAR measures the GHS *urban centre*, not the
administrative city (ADR 0001), so every emissions row says so and carries the evidence:

| Column | Why |
|---|---|
| `urban_centre_emissions` (not `value`), `territory_basis = 'ghs_urban_centre'` | the figure is the urban centre's, by name |
| `uc_share_inside_admin`, `low_urban_overlap`, `suspected_crosswalk_error` | how far that territory is the city's |
| `crosswalk_review_status` | whether a person still has to fix the city's match |
| `mapping_quality`, `sector_mapping_review_status` | how good the EDGAR → GPC label is (ADR 0002) |
| `edgar_version_id`, `ucdb_version_id`, `gb_version_id` | which files the row comes from (→ `dataset_versions`) |

The crosswalk's and the sector map's review statuses are named apart because both are on
the same row. All flags come from `city_overlap`, and a test checks that every model
carries the same values. `city_overlap` adds `admin_area_mismatch` (boundary area off the
official one by more than 25%: Accra, Buenos Aires) and a `flags` array naming every flag
that is set, plus `crosswalk_needs_review`.

On the real data, the six largest urban-centre emitters (Jakarta, Tokyo, Seoul, Bangkok,
Cairo, Delhi) all have `low_urban_overlap`: Jakarta's urban centre is 14% inside DKI
Jakarta. That is why the label is on the column name and not only in the docs.

**No GPC totals.** `city_emissions` stays at the EDGAR-sector grain with GPC-aligned labels
per row. Energy and Residential both map to GPC I and Industry is `mixed` (I+IV), so a
per-GPC sum would add approximate mappings together and hide it.

**Trend over uneven years.** EDGAR's years are 1975, 1990, 2000, 2005, 2010, 2015, 2020
and 2022. Each trend row names `prev_year` (the previous *available* year) and gives
`annualised_change_pct`, the compound annual rate, so a 15-year and a 2-year gap compare.
Nothing is interpolated. Formulas: `macros/change_pct.sql`, tested on hand-computed cases.

**GeoJSON.** `city_boundaries` stores geometries as `jsonb` (RFC 7946: WGS84, exterior
rings counter-clockwise, 6 decimals ≈ 0.1 m), so the API needs no PostGIS function and no
access outside `reporting`. Both the boundary and the urban centre are included, so a map
can show the mismatch. All 25 boundaries total ~175 kB; no further simplification.
Licences are carried per row: geoBoundaries' licence varies by country.

**Numeric types.** Exact values are declared `pg_catalog.numeric`: Postgres `numeric`
with no precision, which stores EDGAR's figures exactly. dbt warns on the bare word
`numeric`, a warning written for warehouses that round an unconstrained numeric. Postgres
does not, so the type is spelled out instead of rounding the data to silence it.

**Tests.** Per model: primary key, row counts against `modelled`, accepted values, and
every `*_version_id` must exist in `dataset_versions` and be the **current** version of
its source (`tests/generic/is_current_version.sql`). Plus:

| Test | Checks |
|---|---|
| `assert_trend_reconciles_with_sectors` | trend totals = sum of `city_emissions` over every sector in the sector map |
| `assert_trend_ghg_not_below_co2` | GHG ≥ CO2 still holds after summing sectors |
| `assert_change_pct_known_cases` | change and annualised formulas on hand-computed values (incl. zero and missing) |
| `assert_cities_latest_ghg` | `latest_urban_centre_ghg_t_co2e` is the last year's GHG total, in t CO2e |
| `assert_reporting_flags_consistent` | every model carries the same flags as `city_overlap` |
| `assert_known_findings_flagged` | Accra and Buenos Aires are flagged as documented; fails on purpose when fixed, so a flag never vanishes silently |
| `city_boundaries` expressions | valid MultiPolygons, CCW rings, area within 0.1% after rounding, bbox contains both shapes |
| `city_overlap` expressions | each flag agrees with its threshold on the row; `flags` names exactly the flags set |
| `assert_api_reader_can_read_reporting` | after every rebuild, the reader can read each `reporting` table and has no `USAGE` on `raw` or `modelled` |

The access test was checked by revoking `SELECT` on one table: the test failed, and
rebuilding that table restored the grant through the default privileges.

## Revisions between EDGAR versions

Sources are versioned in `raw` (a new file is a new `dataset_version_id`), so a revision is
the difference between two versions. No snapshot is needed.

- `stg_edgar__crosswalk_emissions_by_version` reads **every** EDGAR version this target
  may use, for the 25 crosswalk urban centres only. It uses the same macro as the
  current-version staging model (`macros/unpivot_edgar_emissions.sql`), but filters before
  unpivoting, so each extra version costs 25 records, not 11,686.
- `fct_city_emissions_by_version` adds the city and the pollutant metadata. Its
  current-version slice must equal `fct_city_emissions` cell for cell, which ties the
  revisions to what reporting serves.
- `reporting.city_emission_revisions` pairs each EDGAR version with the next one loaded
  (across `source_key` too, so a v2025 release would be compared with the last v2024 file)
  and keeps only cells that `changed`, were `added` or were `removed`. Each row has both
  values, `change`, `change_pct`, the urban-centre label and today's overlap flags.

**Version tests.** Every other reporting model requires its `*_version_id` columns to be
the *current* version. `from_edgar_version_id` and `to_edgar_version_id` hold older versions
by design, so they are only tied to `dataset_versions` and to EDGAR, and the pair must be
in load order. `tests/transform/test_reporting_manifest.py` lists those two columns as the
only exemptions. It fails if one of them gains the current-version test, or if any other
version column lacks it.

**Tested with real changes.** On `warehouse_test` (389 rows), `assert_revisions_known_changes`
(test target only) requires exactly the following, and nothing else:

| Pair | `revision_type` | Cells |
|---|---|---|
| version 1 → 2 | `changed` | the five crosswalk cells, with their factors |
| version 1 → 2 | `removed` | every cell of Dakar (192) |
| version 2 → 3 | `added` | every cell of Dakar (192), equal to the removed values cell for cell |

The ×2 change to the non-crosswalk urban centre must not appear. Each branch was checked
to fail: a wrong expected factor, `removed` expected for the wrong city (192 failures), and
one corrupted `added` value (1 failure). On the real warehouse the table is empty until a
second EDGAR version is loaded.

## Snapshots

**Where history comes from.** Two kinds of change, two mechanisms:

| What changes | How it is recorded | Why |
|---|---|---|
| Source data (EDGAR, GHS-UCDB, geoBoundaries) | a new `raw.dataset_versions` row; `raw` is append-only. EDGAR revisions are modelled by comparing versions: [`city_emission_revisions`](#revisions-between-edgar-versions) | rebuildable from `raw` at any time; captures every release even if two are loaded between dbt runs |
| The crosswalk and the sector map (seeds, **edited in place**) | dbt snapshots `snap_city_crosswalk`, `snap_edgar_sector_map` in `modelled` | git records *who changed what and why*; the snapshot records *when it went live in this warehouse*, queryable in SQL |

The sector map needs a snapshot as much as the crosswalk does: changing it relabels every
reported figure (`gpc_sector`, `mapping_quality`) while `edgar_version_id` stays the same,
so comparing dataset versions cannot see it. Emissions are not snapshotted: that would
duplicate `raw` and miss any version loaded between two runs.

Both use the `check` strategy on the columns that define the match or the mapping:

- crosswalk: `edgar_uc_id`, `gb_shape_id`, `gb_adm_level`, `gb_shape_name`,
  `review_status`, `match_note`, `official_area_km2`
- sector map: `gpc_sector_code`, `gpc_sector`, `mapping_quality`, `review_status`, `note`

`hard_deletes = new_record` records a removed city or sector as a row with
`dbt_is_deleted = True` (it copies the last known values). `git_commit` holds the commit
the run was built from, with `-dirty` if the working tree had uncommitted changes. It is
recorded, not compared, and set automatically by `scripts/dbt-build.sh` (see
[Quick start](running.md#quick-start)). A `dbt build` run some other way records `unknown`.

Tests: at most one current row per key, and the current rows equal the seeds on every
tracked column (`assert_snapshots_match_seeds`). Checked on `warehouse_test` by editing
Kigali's note and deleting the Waste sector, then reverting. Each step gave one new row,
the deletion gave a `dbt_is_deleted` row, and the revert gave a third current row.

### Back up the snapshots: they cannot be rebuilt

Every other table comes back from the source files and `raw`. **Snapshot history does
not.** `docker compose down -v` (or a lost volume) deletes it for good. `dbt build
--full-refresh` does not touch snapshots (checked), but dropping the volume does.

Back up (custom format, both snapshot tables, owner and grants included):

```bash
mkdir -p backups
docker compose exec -T db pg_dump -U climate -d warehouse --format=custom \
  --table='modelled.snap_*' > backups/snapshots_$(date +%Y%m%dT%H%M%S).dump
```

Restore into a new volume **before the first `dbt build`**, so dbt continues the history
instead of starting a new one:

```bash
docker compose exec -T db pg_restore -U climate -d warehouse --clean --if-exists \
  < backups/snapshots_<timestamp>.dump
```

Round trip checked on `warehouse_test`: dump, drop both tables, restore. The contents
were identical by checksum, the owner was still the pipeline role, and the next `dbt snapshot`
added no rows. `backups/` is git-ignored; copy the files somewhere off the machine too.
The backup is still manual: Dagster (Stage 5) does not run it yet (see Next steps).
