-- Grain: one row per city. Serves GET /cities/{id}/boundary. GeoJSON-ready geometries of
-- the administrative boundary and of the GHS urban centre (the territory of the
-- emissions), so a map can show both. No PostGIS type leaves the database: the API reads
-- jsonb and needs no access outside the reporting schema.
-- RFC 7946: WGS84 longitude/latitude, exterior rings counter-clockwise, 6 decimals (~0.1 m).
-- bbox [west, south, east, north] covers both shapes, rounded outward so it still
-- contains the rounded coordinates.
with cities as (
    select city_id, uc_id, gb_shape_id, gb_shape_name, gb_adm_level, admin_geom, gb_version_id
    from {{ ref('dim_city') }}
),

urban_centres as (
    select uc_id, dataset_version_id as ucdb_version_id, st_transform(geom, 4326) as uc_geom
    from {{ ref('stg_ghs_ucdb__urban_centres') }}
),

versions as (
    select dataset_version_id, source_url, license
    from {{ ref('stg_raw__dataset_versions') }}
),

shapes as (
    select
        c.*,
        u.ucdb_version_id,
        st_forcepolygonccw(c.admin_geom) as admin_ccw,
        st_forcepolygonccw(u.uc_geom) as uc_ccw,
        st_collect(c.admin_geom, u.uc_geom) as both_geom
    from cities as c
    inner join urban_centres as u using (uc_id)
)

select
    s.city_id::text as city_id,
    s.gb_shape_id::text as gb_shape_id,
    s.gb_shape_name::text as gb_shape_name,
    s.gb_adm_level::text as gb_adm_level,
    st_asgeojson(s.admin_ccw, 6)::jsonb as boundary_geojson,
    st_asgeojson(s.uc_ccw, 6)::jsonb as urban_centre_geojson,
    array[
        floor(st_xmin(s.both_geom) * 1e6) / 1e6,
        floor(st_ymin(s.both_geom) * 1e6) / 1e6,
        ceil(st_xmax(s.both_geom) * 1e6) / 1e6,
        ceil(st_ymax(s.both_geom) * 1e6) / 1e6
    ]::double precision[] as bbox,
    o.admin_area_km2,
    o.official_area_km2,
    o.admin_area_vs_official,
    o.admin_area_mismatch,
    gb.license::text as boundary_license,
    gb.source_url::text as boundary_source_url,
    uc.license::text as urban_centre_license,
    s.gb_version_id::bigint as gb_version_id,
    s.ucdb_version_id::bigint as ucdb_version_id
from shapes as s
inner join {{ ref('city_overlap') }} as o using (city_id)
left join versions as gb on gb.dataset_version_id = s.gb_version_id
left join versions as uc on uc.dataset_version_id = s.ucdb_version_id
