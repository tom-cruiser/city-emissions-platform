{{ config(
    materialized='table',
    indexes=[{'columns': ['shape_id']}, {'columns': ['geom'], 'type': 'gist'}]
) }}
-- One row per geoBoundaries feature (current version of each country file), parsed from
-- GeoJSON and repaired the same way as the urban centres. WGS84 (EPSG:4326, RFC 7946).
-- Table, not view: parsing and repairing ~7k features (5.6k Brazilian municipalities) is
-- the expensive step, and the tests and dim_city read it.
with versions as (
    select dataset_version_id, source_key
    from {{ ref('stg_raw__current_versions') }}
    where source_name = 'geoboundaries'
),

parsed as (
    select
        f.dataset_version_id,
        f.feature_index,
        v.source_key,
        f.properties,
        st_setsrid(st_geomfromgeojson(f.geometry::text), 4326) as geom_source
    from {{ source('raw', 'geoboundaries_features') }} as f
    inner join versions as v using (dataset_version_id)
)

select
    dataset_version_id,
    feature_index,
    split_part(source_key, '_', 1) as country_iso3,
    split_part(source_key, '_', 2) as adm_level,
    properties ->> 'shapeID' as shape_id,
    properties ->> 'shapeName' as shape_name,
    properties ->> 'shapeGroup' as shape_group,
    properties ->> 'shapeType' as shape_type,
    st_isvalid(geom_source) as geom_was_valid,
    st_multi(st_collectionextract(st_makevalid(geom_source), 3))::geometry(MultiPolygon, 4326) as geom
from parsed
