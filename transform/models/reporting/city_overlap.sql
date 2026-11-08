-- Grain: one row per city. Serves GET /cities/{id}/overlap and the flags every other
-- reporting model carries (they read their flags from here, so they cannot disagree).
-- Overlap between the city's GHS urban centre (the territory of its EDGAR emissions) and
-- its administrative boundary; method in ADR 0001.
with overlap as (
    select * from {{ ref('city_territory_overlap') }}
),

cities as (
    select city_id, match_note, official_area_km2, admin_area_vs_official
    from {{ ref('dim_city') }}
),

flagged as (
    select
        o.*,
        c.match_note,
        c.official_area_km2,
        c.admin_area_vs_official,
        -- Null official area = not known to be wrong, so false (not null): the flag means
        -- "a sourced official area disagrees with the polygon".
        coalesce(abs(c.admin_area_vs_official) > {{ var('admin_area_tolerance') }}, false) as admin_area_mismatch
    from overlap as o
    inner join cities as c using (city_id)
)

select
    city_id::text as city_id,
    uc_id::integer as uc_id,
    'ghs_urban_centre'::text as territory_basis,
    uc_share_inside_admin::double precision as uc_share_inside_admin,
    admin_share_covered::double precision as admin_share_covered,
    iou::double precision as iou,
    uc_area_km2::double precision as uc_area_km2,
    admin_area_km2::double precision as admin_area_km2,
    intersection_area_km2::double precision as intersection_area_km2,
    official_area_km2::numeric as official_area_km2,
    admin_area_vs_official::double precision as admin_area_vs_official,
    low_urban_overlap::boolean as low_urban_overlap,
    suspected_crosswalk_error::boolean as suspected_crosswalk_error,
    admin_area_mismatch::boolean as admin_area_mismatch,
    min_urban_overlap::numeric as min_urban_overlap,
    suspect_crosswalk_overlap::numeric as suspect_crosswalk_overlap,
    {{ var('admin_area_tolerance') }}::numeric as admin_area_tolerance,
    review_status::text as crosswalk_review_status,
    match_note::text as match_note,
    array_remove(array[
        case when low_urban_overlap then 'low_urban_overlap' end,
        case when suspected_crosswalk_error then 'suspected_crosswalk_error' end,
        case when admin_area_mismatch then 'admin_area_mismatch' end,
        case when review_status = 'needs_review' then 'crosswalk_needs_review' end
    ], null)::text[] as flags,
    ucdb_version_id::bigint as ucdb_version_id,
    gb_version_id::bigint as gb_version_id
from flagged
