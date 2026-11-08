-- Grain: one row per city x pollutant x EDGAR sector x year, current EDGAR version.
-- Serves GET /cities/{id}/emissions. The figures are the emissions of the city's GHS
-- URBAN CENTRE (territory_basis), not of its administrative boundary: every row carries
-- how far the two overlap and whether the city's match is under review.
-- Stays at the EDGAR-sector grain: GPC labels are per row and never summed (several EDGAR
-- sectors map to the same or to mixed GPC sectors, ADR 0002).
with emissions as (
    select * from {{ ref('fct_city_emissions') }}
),

sector_map as (
    select edgar_sector, review_status as sector_mapping_review_status
    from {{ ref('edgar_sector_map') }}
),

overlap as (
    select * from {{ ref('city_overlap') }}
)

select
    e.city_id::text as city_id,
    e.pollutant_code::text as pollutant_code,
    e.edgar_sector::text as edgar_sector,
    e.year::integer as year,
    e.territory_basis::text as territory_basis,
    e.value::numeric as urban_centre_emissions,
    e.pollutant::text as pollutant,
    e.unit::text as unit,
    e.is_greenhouse_gas::boolean as is_greenhouse_gas,
    e.is_ghg_total::boolean as is_ghg_total,
    e.gpc_sector_code::text as gpc_sector_code,
    e.gpc_sector::text as gpc_sector,
    e.mapping_quality::text as mapping_quality,
    s.sector_mapping_review_status::text as sector_mapping_review_status,
    e.uc_id::integer as uc_id,
    o.uc_share_inside_admin,
    o.low_urban_overlap,
    o.suspected_crosswalk_error,
    o.crosswalk_review_status,
    e.dataset_version_id::bigint as edgar_version_id,
    o.ucdb_version_id,
    o.gb_version_id
from emissions as e
inner join overlap as o using (city_id)
left join sector_map as s using (edgar_sector)
