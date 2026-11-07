-- Grain: one row per crosswalk city. How far the territory EDGAR's emissions describe
-- (the GHS urban centre) overlaps the administrative boundary shown for the city.
-- Method and thresholds: ADR 0001; computation: macros/overlap_metrics.sql.
--   low_urban_overlap          share of the urban centre inside the boundary < var('min_urban_overlap')
--                              (0.5): the emissions figure describes a substantially different territory.
--   suspected_crosswalk_error  share < var('suspect_crosswalk_overlap') (0.01): the match itself is
--                              probably wrong (warn test). review_status says whether it is known.
-- Table: expensive geometry operations; 25 rows.
with cities as (
    select city_id, uc_id, review_status, gb_version_id, admin_geom
    from {{ ref('dim_city') }}
),

urban_centres as (
    select uc_id, dataset_version_id as ucdb_version_id, geom as uc_geom
    from {{ ref('stg_ghs_ucdb__urban_centres') }}
),

overlap_input as (
    select c.*, u.ucdb_version_id, u.uc_geom
    from cities as c
    inner join urban_centres as u using (uc_id)
),

metrics as (
    {{ overlap_metrics('overlap_input') }}
)

select
    city_id,
    uc_id,
    review_status,
    uc_share_inside_admin,
    admin_share_covered,
    iou,
    uc_share_inside_admin_geodesic,
    uc_area_km2,
    admin_area_km2,
    intersection_area_km2,
    low_urban_overlap,
    suspected_crosswalk_error,
    min_urban_overlap,
    suspect_crosswalk_overlap,
    ucdb_version_id,
    gb_version_id
from metrics
