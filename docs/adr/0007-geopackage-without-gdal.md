# ADR 0007: Read the GHS-UCDB GeoPackage without GDAL

- **Status:** Accepted; implemented in Stage 2 (`ingestion/gpkg.py`), recorded in Stage 8.
- **Date:** 2026-11-09 (decision taken 2026-11-06)

## Context

GHS-UCDB is published as one 285 MB GeoPackage. The usual way to read it is GDAL, through
`ogr2ogr`, Fiona, pyogrio or GeoPandas. GDAL is a large native dependency: it makes the
pipeline image much bigger, ties the build to system libraries, and does far more than we
need. We need one layer of 11,422 polygons, its attributes, and its geometry handed to
PostGIS unchanged. PostGIS already does every geometry operation (repair, reprojection,
area, overlap).

A GeoPackage is a SQLite file. Each geometry is standard WKB behind a small, documented
header (OGC 12-128r19, section 2.1.3).

## Decision

Read the file with the standard library's `sqlite3`, in read-only mode, and parse the
GeoPackageBinary header ourselves (magic, version, flags, SRS id, envelope). The WKB
after it goes to PostGIS untouched (`ST_GeomFromWKB`), so no coordinate is rewritten in
Python. Anything outside the standard is rejected: other versions, the
ExtendedGeoPackageBinary flag, a wrong `application_id`.

Because we own this parser, every load cross-checks it against PostGIS (`gpkg_header`
load check: SRS id and envelope against the bounds PostGIS computes from the WKB). The
parser is unit-tested on constructed blobs (both byte orders, every envelope size,
malformed input) and on the 25 real polygons against an independent WKB reader.

## Consequences

- `ingestion/gpkg.py` is 125 lines, with no native dependencies. The pipeline image
  installs no GDAL.
- It reads only what we use: one feature table, no rasters, tiles or extensions.
- If GHS-UCDB ever ships Extended geometry types, the load fails loudly rather than
  misreading them.

## When we would choose differently

- **More formats or sources.** Shapefile, FileGDB or GML would make GDAL worth its cost;
  writing one reader per format would not.
- **Geometry work in Python** (reprojection, repair before load) instead of in PostGIS.
- **GDAL already present**, for example a GeoPandas-based team or base image, where the
  extra dependency costs nothing.
- **`ogr2ogr` straight into PostGIS** if load speed mattered more than loading through
  the same versioned, checked path as the other sources.
