-- Grain: one row per crosswalk city. Serves GET /cities. The match (urban centre and
-- boundary), its review status and flags, the years covered, and the latest GHG total of
-- the city's URBAN CENTRE (not of its administrative boundary).
with cities as (
    select * from {{ ref('dim_city') }}
),

overlap as (
    select * from {{ ref('city_overlap') }}
),

ghg as (
    select
        city_id,
        min(year) as first_year,
        max(year) as last_year,
        (array_agg(urban_centre_emissions order by year desc))[1] as latest_ghg,
        (array_agg(unit order by year desc))[1] as latest_ghg_unit,
        min(edgar_version_id) as edgar_version_id
    from {{ ref('city_emissions_trend') }}
    where is_ghg_total
    group by city_id
)

select
    c.city_id::text as city_id,
    c.city_name::text as city_name,
    c.country_iso3::text as country_iso3,
    c.uc_id::integer as uc_id,
    c.edgar_uc_name::text as edgar_uc_name,
    c.gb_adm_level::text as gb_adm_level,
    c.gb_shape_id::text as gb_shape_id,
    c.gb_shape_name::text as gb_shape_name,
    'ghs_urban_centre'::text as territory_basis,
    g.first_year::integer as first_year,
    g.last_year::integer as last_year,
    g.latest_ghg::numeric as latest_urban_centre_ghg_t_co2e,
    o.uc_share_inside_admin,
    o.low_urban_overlap,
    o.suspected_crosswalk_error,
    o.admin_area_mismatch,
    o.crosswalk_review_status,
    o.match_note,
    o.flags,
    g.edgar_version_id::bigint as edgar_version_id,
    o.ucdb_version_id,
    o.gb_version_id
from cities as c
inner join overlap as o using (city_id)
left join ghg as g using (city_id)
-- latest_urban_centre_ghg_t_co2e is only in t CO2e if the GHG pollutant's unit says so:
-- tests/assert_cities_latest_ghg.sql checks the unit and the value.
