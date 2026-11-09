# Ingestion

Dataset versions, samples, the synthetic fixture and GHS-UCDB load checks. Back to the [README](../README.md).

## How ingestion works

**Dataset versions.** Every loaded file gets a row in `raw.dataset_versions` with its
source URL, SHA-256, size, download time, load time and licence. Every raw row carries
`dataset_version_id`. The modelled and reporting layers will carry it forward, so any
number can be traced back to the exact bytes it came from.

**Idempotency.** `(source_name, source_key, file_sha256)` is unique, and registration
uses `INSERT ... ON CONFLICT DO NOTHING`. The same bytes give a no-op. Changed bytes
give a new version, and the old one stays (raw is append-only). This is also safe when
two loads race.

**Failure handling.**
- Each file loads in its own transaction, so a failure leaves nothing half-written and
  never undoes files that already loaded.
- Downloads retry timeouts, 429 and 5xx with exponential backoff (~3 min worst case).
  geoBoundaries is served via GitHub LFS, which returns intermittent 504s.
- 404 and other client errors fail immediately.
- A failing country is reported, the run continues, and the CLI exits non-zero.

**Raw is untouched.** EDGAR rows are stored as JSON exactly as read, plus the unit the
source declares (`ton/year`). Boundaries are stored as GeoJSON. Typing, unpivoting,
unit handling, name repair and conversion to PostGIS geometry belong to the modelled
layer (Stage 3).

**Samples.** `data/sample/manifest.json` lists every committed file and where it came
from. Each file is loaded with the same loader as the real data.

| Sample file | `origin` | Built by | Provenance recorded |
|---|---|---|---|
| geoBoundaries GeoJSON (24 files) | `sample` | `make-sample` cuts the crosswalk cities out of the latest downloads | upstream URL + `upstream_sha256` + download time |
| GHS-UCDB GeoPackage | `sample` | `make-sample` copies the 25 crosswalk urban centres of one layer out of the latest download | upstream URL + `upstream_sha256` (of the zip) + download time; licence text lists the changes |
| EDGAR workbook | `synthetic` | `make-synthetic` generates it, no download involved | `source_url = synthetic:ingestion/synthetic.py`, no upstream hash |

### Synthetic EDGAR fixture

`ingestion/synthetic.py` writes `EDGAR_emiss_on_UCDB_2024_SYNTHETIC.xlsx`:

- **Same structure as EDGAR v2024.** Same sheet names, the `Units` row, and the 195-column
  header (`ID_UC_G0`, `UC_name`, `UC_country`, then `EMI_<pollutant>_<sector>_<year>`).
  The generated header was checked against the real file and is identical.
- **Invented values.** Every number comes from a seeded random generator. Columns
  stay internally consistent: total GHG in CO2e is never below CO2, and nothing is
  negative.
- **Deliberate edge cases** for the modelled layer:
  - the mis-encoded names exactly as EDGAR has them (`SÃ£o Paulo`, `MÃ©xico`);
  - a second `Lagos, Nigeria` with a fake ID (990001), so a join by name would
    double-count Lagos;
  - an urban centre outside the crosswalk (990002);
  - a sector that is zero in every year.
- **Clearly labelled.** The filename, the first sheet ("SYNTHETIC DATA - NOT EDGAR"),
  the manifest and `raw.dataset_versions.origin = 'synthetic'` all say so.
- **Byte-for-byte reproducible.** An `.xlsx` is a zip, and openpyxl stamps entries and
  the `modified` property with the current time. The generator pins both, so
  regenerating gives the same SHA-256 and therefore no new dataset version.

The urban-centre IDs and names in it are real. They come from the GHS Urban Centre
Database (CC BY 4.0) and are needed to match the crosswalk.

**Re-published versions.** Two more files re-publish the same release, the way a source
can silently fix a file under the same name. Loaded in order, they make three dataset
versions of EDGAR `v2024`, which together produce every kind of revision for a crosswalk
city (`synthetic.VARIANTS`):

| Version | File | Compared with the previous one |
|---|---|---|
| 1 | `…_SYNTHETIC.xlsx` | (the original) |
| 2 | `…_SYNTHETIC_REVISED.xlsx` | the cells below **changed**; Dakar's row **removed** |
| 3, current | `…_SYNTHETIC_REVISED_2.xlsx` | Dakar's row **added** back, values as in version 1 |

The removal happens in a non-current version on purpose. If a crosswalk city were
missing from the current version, the build would fail (correctly), and a row outside the
crosswalk would never reach `city_emission_revisions`. All three are generated from the same
random draws, so they differ *only* as listed (`test_republications_differ_only_as_documented`).
The corrected cells are:

| Urban centre | Sector, year | Pollutants | Factor |
|---|---|---|---|
| Kigali (597) | Transport 2022 | CO2 and GHG | ×1.25 |
| Nairobi (1717) | Energy 1990 | CO2 and GHG | ×0.8 |
| Lagos (1289) | Residential 2015 | PM2.5 | ×1.5 |
| Synthetic Town (990002, not in the crosswalk) | Waste 2020 | CO2 and GHG | ×2 |

CO2 and GHG are scaled together, so GHG ≥ CO2 still holds. The manifest orders the files
by `generated_at` and the sample load runs in manifest order, so version 3 is current.

## GHS-UCDB urban centres

EDGAR computes emissions per GHS urban centre. To compare those territories with the
administrative boundaries, the urban-centre polygons are loaded from
[GHS-UCDB R2024A V1.2](https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php)
(a 277 MB zip holding one 285 MB GeoPackage with 16 layers).

- **One layer.** All 15 thematic layers repeat the same 11,422 polygons. Only
  `GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A` is loaded: ID, names, country,
  area, population, geometry.
- **No GDAL.** `ingestion/gpkg.py` reads the file with stdlib `sqlite3` and parses the
  GeoPackageBinary header (magic, flags, SRS id, envelope) itself. The WKB after the header
  goes to PostGIS untouched (`ST_GeomFromWKB`). Header parsing is tested on constructed
  blobs (both byte orders, every envelope size, malformed input) and on the 25 real
  polygons, against an independent pure-Python WKB reader.
- **Stored as published.** Native CRS (World Mollweide, ESRI:54009), no reprojection, no
  repair. The downloaded zip is the dataset version. The extracted `.gpkg` next to it is
  a cache named after the zip's hash.

### Load checks

Every GHS-UCDB load runs these checks in the same transaction as the rows. A failing
check raises and rolls the file back. Passes and warnings go to `raw.load_checks`.

| Check | Fails when | Result on the full file (11,422 polygons) |
|---|---|---|
| `row_count` | rows in raw ≠ features in the layer | pass: 11,422 = 11,422 |
| `gpkg_header` | a blob's SRS id ≠ the layer's, or its envelope ≠ the bounds PostGIS computes from the WKB | pass: 0 mismatches |
| `srid` | layer SRS is not ESRI:54009, it is missing from `spatial_ref_sys`, or a stored SRID differs | pass: all 54009 (`World_Mollweide`, present in the stock PostGIS image) |
| `geometry_type` | anything other than (MULTI)POLYGON | pass: 11,422 MULTIPOLYGON |
| `geometry_valid` | never fails; warns on invalid polygons | **warn: 22 invalid** (all ring self-intersections, none of our 25 cities); `ST_CollectionExtract(ST_MakeValid(geom), 3)` repairs all 22 |
| `area_vs_source` | warns if `ST_Area` differs from the source's `GC_UCA_KM2_2025` by > 5% | pass: identical for all 11,422 (the polygons are unions of 1 km² Mollweide cells) |
| `id_match_edgar` | null or duplicate IDs, or a crosswalk city missing from UCDB | **warn: 11,422 matched, 264 EDGAR-only, 0 UCDB-only**; all 25 crosswalk cities present in both |

Inspect them:

```bash
docker compose exec db psql -U climate -d warehouse -c \
  "SELECT check_name, status, detail->>'summary' FROM raw.load_checks ORDER BY dataset_version_id, check_name"
```

### Overlap with administrative boundaries (built in Stage 3)

Computed in dbt, not ingestion. The full decision and its reasoning are in
[ADR 0001](adr/0001-urban-centre-overlap.md).

- **Staging repairs geometry** with `ST_CollectionExtract(ST_MakeValid(geom), 3)`. Raw is
  never modified.
- **Areas are compared in Mollweide** (ESRI:54009), with boundaries transformed from 4326.
- **Flag** `low_urban_overlap` when *share of the urban centre inside the boundary* <
  `var('min_urban_overlap')`, **default 0.5**. IoU and *share of the boundary covered*
  are reported as information.
- **The 0.5 is a methodology decision for domain specialists** (city GHG inventory
  practitioners), not an engineering one. It is a dbt var so it can be changed without
  touching code.

**Is Mollweide safe for this?** For ratios, yes. For absolute km², not quite. PROJ's
Mollweide is a spherical projection applied with the WGS84 semi-major axis, so absolute
areas of our 25 boundaries are off by **up to 0.67%** (latitude-dependent) against
ellipsoidal `geography` areas. The error is nearly the same for both polygons of a city,
so it cancels in the overlap share. The share computed in Mollweide differs from the
geodesic one by at most **1.9 × 10⁻⁵** across all 25 cities (asserted in
`tests/ingestion/test_ghs_ucdb_db.py`, and on every dbt build in `city_territory_overlap`). Absolute boundary areas, where reported, should use
`geography`.
