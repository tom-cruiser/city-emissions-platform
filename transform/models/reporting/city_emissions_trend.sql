-- Grain: one row per city x pollutant x year: all EDGAR sectors summed, current EDGAR
-- version. Serves GET /cities/{id}/trend. Summing sectors WITHIN a pollutant is valid;
-- pollutants are never added together (GHG already contains CO2).
-- EDGAR's years are not annual (1975, 1990, 2000, 2005, 2010, 2015, 2020, 2022): each row
-- names the previous available year and gives an annualised rate. No year is filled in.
with yearly as (
    select
        city_id, pollutant_code, year,
        pollutant, unit, is_greenhouse_gas, is_ghg_total, territory_basis, uc_id,
        uc_share_inside_admin, low_urban_overlap, suspected_crosswalk_error,
        crosswalk_review_status, edgar_version_id, ucdb_version_id, gb_version_id,
        sum(urban_centre_emissions) as urban_centre_emissions,
        count(*) as sector_count
    from {{ ref('city_emissions') }}
    group by
        city_id, pollutant_code, year,
        pollutant, unit, is_greenhouse_gas, is_ghg_total, territory_basis, uc_id,
        uc_share_inside_admin, low_urban_overlap, suspected_crosswalk_error,
        crosswalk_review_status, edgar_version_id, ucdb_version_id, gb_version_id
),

with_prev as (
    select
        *,
        lag(year) over w as prev_year,
        lag(urban_centre_emissions) over w as prev_urban_centre_emissions
    from yearly
    window w as (partition by city_id, pollutant_code order by year)
)

select
    city_id::text as city_id,
    pollutant_code::text as pollutant_code,
    year::integer as year,
    territory_basis::text as territory_basis,
    urban_centre_emissions::numeric as urban_centre_emissions,
    pollutant::text as pollutant,
    unit::text as unit,
    is_greenhouse_gas::boolean as is_greenhouse_gas,
    is_ghg_total::boolean as is_ghg_total,
    sector_count::integer as sector_count,
    prev_year::integer as prev_year,
    prev_urban_centre_emissions::numeric as prev_urban_centre_emissions,
    {{ change_pct('urban_centre_emissions', 'prev_urban_centre_emissions') }} as change_since_prev_pct,
    {{ annualised_change_pct('urban_centre_emissions', 'prev_urban_centre_emissions', 'year - prev_year') }}
        as annualised_change_pct,
    uc_id::integer as uc_id,
    uc_share_inside_admin,
    low_urban_overlap,
    suspected_crosswalk_error,
    crosswalk_review_status,
    edgar_version_id,
    ucdb_version_id,
    gb_version_id
from with_prev
