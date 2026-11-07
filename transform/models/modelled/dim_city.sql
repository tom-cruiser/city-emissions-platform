-- One row per crosswalk city: the urban centre and administrative boundary it is matched
-- to (by ID, never by name), the review status of that match, and the boundary's
-- geodesic area against the official one where sourced.
-- Table: 25 rows, but it carries the boundary geometry that the overlap model reads.
with crosswalk as (
    select * from {{ ref('city_crosswalk') }}
),

urban_centres as (
    select * from {{ ref('stg_edgar__urban_centres') }}
),

boundaries as (
    select * from {{ ref('stg_geoboundaries__boundaries') }}
),

joined as (
    select
        c.city_id,
        c.city_name,
        c.country_iso3,
        c.edgar_uc_id as uc_id,
        u.uc_name as edgar_uc_name,
        u.country_name as edgar_country_name,
        u.name_lossy as edgar_name_lossy,
        c.gb_adm_level,
        c.gb_shape_id,
        c.gb_shape_name,
        b.shape_name as gb_shape_name_source,
        c.review_status,
        c.match_note,
        c.official_area_km2,
        c.official_area_source,
        st_area(b.geom::geography) / 1e6 as admin_area_km2,
        u.dataset_version_id as edgar_version_id,
        b.dataset_version_id as gb_version_id,
        b.geom as admin_geom
    from crosswalk as c
    inner join urban_centres as u on u.uc_id = c.edgar_uc_id
    inner join boundaries as b on b.shape_id = c.gb_shape_id
)

select
    *,
    -- +0.25 = boundary 25% larger than the official area; null where no official area yet.
    admin_area_km2 / official_area_km2 - 1 as admin_area_vs_official
from joined
