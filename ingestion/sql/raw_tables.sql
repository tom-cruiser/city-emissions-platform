-- Raw layer DDL. Idempotent: safe to run before every load.
-- Rule for this schema: rows are only ever INSERTed. Never updated, never deleted.

-- One row per source file we have loaded. This is the "dataset version":
-- every downstream row carries dataset_version_id back to here.
CREATE TABLE IF NOT EXISTS raw.dataset_versions (
    dataset_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name     text        NOT NULL,  -- e.g. 'edgar_ucdb', 'geoboundaries'
    source_key      text        NOT NULL,  -- which file of that source, e.g. 'v2024', 'RWA_ADM1'
    -- download = fetched from the source; sample = real extract committed to the repo;
    -- synthetic = generated test data with the source's structure (never real values)
    origin          text        NOT NULL
                    CONSTRAINT dataset_versions_origin_check
                    CHECK (origin IN ('download', 'sample', 'synthetic')),
    source_url      text        NOT NULL,  -- where the bytes came from (samples: upstream URL)
    file_path       text        NOT NULL,  -- relative to the repo root
    file_sha256     char(64)    NOT NULL,  -- hash of the exact bytes loaded
    file_size_bytes bigint      NOT NULL,
    upstream_sha256 char(64),              -- samples only: hash of the full file the sample was cut from
    -- download: when fetched. sample: when the upstream file was fetched. synthetic: when generated.
    license         text,
    downloaded_at   timestamptz NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    row_count       integer     NOT NULL,
    -- Same bytes for the same source file = same version. This makes re-runs no-ops.
    UNIQUE (source_name, source_key, file_sha256)
);

COMMENT ON TABLE raw.dataset_versions IS
  'Dataset versions for lineage: one row per loaded source file, identified by its SHA-256.';

-- EDGAR emissions per GHS urban centre, one row per row of the source sheet.
-- The row is kept as JSON exactly as read: typing and unpivoting happen in dbt.
CREATE TABLE IF NOT EXISTS raw.edgar_ucdb_emissions (
    dataset_version_id bigint  NOT NULL REFERENCES raw.dataset_versions,
    source_row_number  integer NOT NULL,  -- 1 = first data row under the header
    source_unit        text    NOT NULL,  -- unit as declared by the source ('ton/year')
    record             jsonb   NOT NULL,  -- {"ID_UC_G0": 597, "UC_name": "Kigali", "EMI_..._2022": 1.2, ...}
    PRIMARY KEY (dataset_version_id, source_row_number)
);

-- geoBoundaries features, one row per GeoJSON feature. Geometry stays GeoJSON here;
-- conversion to PostGIS geometry (and validity repair) happens in the modelled layer.
CREATE TABLE IF NOT EXISTS raw.geoboundaries_features (
    dataset_version_id bigint  NOT NULL REFERENCES raw.dataset_versions,
    feature_index      integer NOT NULL,  -- position in the FeatureCollection
    properties         jsonb   NOT NULL,  -- {"shapeName": ..., "shapeID": ..., "shapeGroup": ..., ...}
    geometry           jsonb   NOT NULL,  -- GeoJSON geometry, WGS84 per RFC 7946
    PRIMARY KEY (dataset_version_id, feature_index)
);

-- GHS-UCDB urban-centre polygons, one row per feature of the GeoPackage layer.
-- Geometry is stored exactly as published: native CRS (World Mollweide, ESRI:54009),
-- no reprojection, and NOT repaired. Invalid polygons are counted by the load checks
-- below and fixed with ST_MakeValid in dbt staging (Stage 3), never here.
CREATE TABLE IF NOT EXISTS raw.ghs_ucdb_urban_centres (
    dataset_version_id bigint   NOT NULL REFERENCES raw.dataset_versions,
    source_row_number  integer  NOT NULL,  -- 1 = first feature in the layer (rowid order)
    properties         jsonb    NOT NULL,  -- every attribute column, untouched ({"ID_UC_G0": 597, ...})
    geom               geometry NOT NULL,  -- WKB from the file + SRID from its gpkg_spatial_ref_sys
    PRIMARY KEY (dataset_version_id, source_row_number)
);

-- Load-time checks: one row per check per dataset version, written in the same
-- transaction as the rows they describe. A check that FAILS raises and rolls the whole
-- file back, so only 'pass' and 'warn' outcomes are ever stored.
CREATE TABLE IF NOT EXISTS raw.load_checks (
    dataset_version_id bigint NOT NULL REFERENCES raw.dataset_versions,
    check_name         text   NOT NULL,  -- e.g. 'row_count', 'srid', 'id_match_edgar', 'geometry_valid'
    status             text   NOT NULL CHECK (status IN ('pass', 'warn')),
    detail             jsonb  NOT NULL,  -- numbers behind the outcome, e.g. {"invalid": 3, "ids": [...]}
    checked_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, check_name)
);
