-- Unit test for macros/overlap_metrics.sql on squares with known answers.
-- Squares are built in Mollweide near (0, 0); the boundary is passed in WGS84 like the
-- real data. Thresholds are fixed here (0.5 / 0.01) so the test does not depend on vars.
-- Returns one row per case whose result differs from the expected one.
with squares (case_name, uc_xmin, uc_size, admin_xmin, admin_ymin, admin_size,
              exp_share, exp_covered, exp_iou, exp_low, exp_suspect) as (
    values
        -- admin is the urban centre shifted by half its width
        ('half overlap',      0, 10000,  5000,     0, 10000, 0.5,    0.5,  1.0 / 3, false, false),
        -- admin contains the urban centre (twice as wide)
        ('admin contains uc', 0, 10000, -5000, -5000, 20000, 1.0,    0.25, 0.25,    false, false),
        -- no overlap
        ('disjoint',          0, 10000, 50000,     0, 10000, 0.0,    0.0,  0.0,     true,  true),
        -- a 0.9 km square inside a 10 km urban centre: share 0.0081 -> suspected error
        ('tiny admin inside', 0, 10000,  1000,  1000,   900, 0.0081, 1.0,  0.0081,  true,  true),
        -- 40% of the urban centre inside: low overlap, but not a suspected error
        ('forty percent',     0, 10000,  6000,     0, 10000, 0.4,    0.4,  0.25,    true,  false)
),

overlap_input as (
    select
        s.*,
        st_multi(st_makeenvelope(uc_xmin, 0, uc_xmin + uc_size, uc_size, 54009))::geometry(MultiPolygon, 54009) as uc_geom,
        st_transform(st_multi(st_makeenvelope(admin_xmin, admin_ymin, admin_xmin + admin_size,
                                              admin_ymin + admin_size, 54009)), 4326) as admin_geom
    from squares as s
),

results as (
    {{ overlap_metrics('overlap_input', min_urban_overlap=0.5, suspect_crosswalk_overlap=0.01) }}
)

select case_name, uc_share_inside_admin, admin_share_covered, iou, low_urban_overlap, suspected_crosswalk_error
from results
where abs(uc_share_inside_admin - exp_share) > 1e-6
   or abs(admin_share_covered - exp_covered) > 1e-6
   or abs(iou - exp_iou) > 1e-6
   or low_urban_overlap is distinct from exp_low
   or suspected_crosswalk_error is distinct from exp_suspect
   or abs(uc_share_inside_admin_geodesic - exp_share) > 1e-3  -- small squares at the equator
