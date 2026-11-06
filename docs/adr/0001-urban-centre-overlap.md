# ADR 0001: Urban-centre vs administrative-boundary overlap

- **Status:** Accepted for implementation in Stage 3. The threshold value is a
  **provisional methodology decision that domain specialists should review**.
- **Date:** 2026-11-06

## Context

EDGAR reports emissions per **GHS urban centre**: a polygon derived from a 1 km
population and built-up grid. The platform presents emissions per **city**, matched to an
**administrative boundary** from geoBoundaries via `transform/seeds/city_crosswalk.csv`.
The two territories can differ a lot. Lagos's urban centre is matched to Lagos State,
Delhi's urban centre (`Ghaziabad [New Delhi]`) extends beyond the NCT of Delhi, and
Tokyo's prefecture includes remote islands. Readers need to see when an emissions figure
describes a substantially different territory from the boundary shown next to it.

## Decision

1. **Where.** Overlap is computed only in dbt (Stage 3). Stage 2 ingestion only loads the
   GHS-UCDB polygons into `raw.ghs_ucdb_urban_centres`, unmodified, and records load
   checks in `raw.load_checks`: row count, GeoPackage header, SRID, geometry type,
   validity, area against the source's own column, and ID match with EDGAR.
2. **Geometry repair.** Raw keeps polygons exactly as published. dbt staging applies
   `ST_CollectionExtract(ST_MakeValid(geom), 3)` (polygonal part only). The load check
   `geometry_valid` confirms that this repairs every polygon.
3. **CRS.** Areas are computed in World Mollweide (ESRI:54009, equal area). That is the
   urban centres' native CRS. geoBoundaries polygons are transformed from EPSG:4326.
   PROJ's Mollweide is spherical, so absolute areas of our boundaries are off by up to
   0.67% against ellipsoidal `geography` areas. The error cancels in a ratio: the overlap
   share differs from the geodesic one by at most 1.9 × 10⁻⁵ across all 25 cities
   (tested). Ratios therefore use Mollweide. Any absolute km² for a boundary uses `geography`.
4. **Metrics** per crosswalk city, with `I = urban centre ∩ admin boundary`:

   | Metric | Formula | Role |
   |---|---|---|
   | `uc_share_inside_admin` | area(I) / area(urban centre) | **flag basis** |
   | `admin_share_covered` | area(I) / area(admin) | information |
   | `iou` | area(I) / area(urban centre ∪ admin) | information |

5. **Flag.** `low_urban_overlap = uc_share_inside_admin < var('min_urban_overlap')`,
   default **0.5**: less than half of the territory EDGAR measured lies inside the boundary
   we label it with. The flag is published with the figure and does not rescale it.

## Why `uc_share_inside_admin`, not IoU

The question the flag answers is whether the emissions figure is *about* this
administrative area. An urban centre lying mostly inside a large boundary (Tokyo
prefecture, Lagos State) is a fair attribution even though IoU is low, because the boundary
also covers rural land. An urban centre lying mostly outside its boundary (a small core
municipality inside a large metro area) is not. IoU penalises both cases the same way, so
it is reported but not used to flag.

## Open for domain review

- **The value 0.5** is an engineering default, not a published standard. It should be set
  by people who work on city GHG inventories (e.g. GPC practitioners). It is a dbt var so it
  can be changed without code changes: `dbt build --vars '{min_urban_overlap: 0.6}'`.
- Whether `admin_share_covered` should also gate the flag (urban centre much smaller than
  the boundary).
- Whether to rescale emissions by area share. Rejected for now: emissions are not uniform
  over space, so an area share is not an emissions share.
