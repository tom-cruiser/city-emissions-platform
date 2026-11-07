{{ config(
    materialized='table',
    indexes=[{'columns': ['uc_id']}, {'columns': ['geom'], 'type': 'gist'}]
) }}
-- One row per GHS-UCDB urban centre (current version), geometry repaired.
-- Table, not view: ST_MakeValid over ~11k polygons is the expensive step, and the tests
-- and the overlap model all read it. Raw keeps the polygons exactly as published.
-- Repair (ADR 0001): ST_MakeValid, keep only the polygonal part, always MultiPolygon.
-- CRS stays World Mollweide (ESRI:54009, equal area), the source's own.
with versions as (
    select dataset_version_id
    from {{ ref('stg_raw__current_versions') }}
    where source_name = 'ghs_ucdb'
)

select
    u.dataset_version_id,
    u.source_row_number,
    (u.properties ->> 'ID_UC_G0')::integer as uc_id,
    u.properties ->> 'GC_UCN_MAI_2025' as uc_name,
    u.properties ->> 'GC_CNT_GAD_2025' as country_name,
    (u.properties ->> 'GC_UCA_KM2_2025')::numeric as source_area_km2,
    (u.properties ->> 'GC_POP_TOT_2025')::numeric as population_2025,
    st_isvalid(u.geom) as geom_was_valid,
    st_multi(st_collectionextract(st_makevalid(u.geom), 3))::geometry(MultiPolygon, 54009) as geom
from {{ source('raw', 'ghs_ucdb_urban_centres') }} as u
inner join versions using (dataset_version_id)
