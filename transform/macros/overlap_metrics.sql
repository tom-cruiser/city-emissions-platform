{#- Overlap of an urban centre with an administrative boundary (ADR 0001).

    `input` is a relation (CTE name) with at least:
      uc_geom    MultiPolygon, SRID 54009 (World Mollweide, equal area)
      admin_geom MultiPolygon, SRID 4326
    Returns every input column plus the metrics below. Used by city_territory_overlap
    and by tests/assert_overlap_metrics_known_cases.sql, which runs it on squares with
    known answers.

    RATIOS are computed in Mollweide (the urban centres' native equal-area CRS; the
    boundary is transformed into it). PROJ's Mollweide is spherical, so absolute areas
    are off by up to 0.67% at our latitudes, but the error cancels in a ratio.
    AREAS in km2 are geodesic (PostGIS geography on the WGS84 ellipsoid).
    uc_share_inside_admin_geodesic is the flag basis recomputed geodesically, so a test
    can check the Mollweide ratio against it.

    The lateral subqueries are fenced with `offset 0`: flattened, each ST_Intersection
    would be recomputed for every column that uses it. -#}
{% macro overlap_metrics(input,
                         min_urban_overlap=var('min_urban_overlap'),
                         suspect_crosswalk_overlap=var('suspect_crosswalk_overlap')) %}
select
    i.*,
    a.uc_m2_geodesic / 1e6 as uc_area_km2,
    a.admin_m2_geodesic / 1e6 as admin_area_km2,
    a.intersection_m2_geodesic / 1e6 as intersection_area_km2,
    a.intersection_m2 / nullif(a.uc_m2, 0) as uc_share_inside_admin,
    a.intersection_m2 / nullif(a.admin_m2, 0) as admin_share_covered,
    a.intersection_m2 / nullif(a.uc_m2 + a.admin_m2 - a.intersection_m2, 0) as iou,
    a.intersection_m2_geodesic / nullif(a.uc_m2_geodesic, 0) as uc_share_inside_admin_geodesic,
    a.intersection_m2 / nullif(a.uc_m2, 0) < {{ min_urban_overlap }} as low_urban_overlap,
    a.intersection_m2 / nullif(a.uc_m2, 0) < {{ suspect_crosswalk_overlap }} as suspected_crosswalk_error,
    {{ min_urban_overlap }}::numeric as min_urban_overlap,
    {{ suspect_crosswalk_overlap }}::numeric as suspect_crosswalk_overlap
from {{ input }} as i
cross join lateral (
    select
        st_area(i.uc_geom) as uc_m2,
        st_area(g.admin_moll) as admin_m2,
        st_area(st_intersection(i.uc_geom, g.admin_moll)) as intersection_m2,
        st_area(g.uc_wgs84::geography) as uc_m2_geodesic,
        st_area(i.admin_geom::geography) as admin_m2_geodesic,
        st_area(st_intersection(g.uc_wgs84, i.admin_geom)::geography) as intersection_m2_geodesic
    from (
        select
            st_transform(i.admin_geom, 54009) as admin_moll,
            st_transform(i.uc_geom, 4326) as uc_wgs84
        offset 0
    ) as g
    offset 0
) as a
{% endmacro %}
