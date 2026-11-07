-- Grain: one row per crosswalk city x pollutant x EDGAR sector x year, for the CURRENT
-- EDGAR version only. dataset_version_id is carried on every row and a test asserts it
-- holds exactly one value.
-- The emissions are those of the city's GHS URBAN CENTRE (territory_basis), not of its
-- administrative boundary: see city_territory_overlap and ADR 0001 before reading them
-- as "emissions inside the city".
-- Table: small (25 x 192 rows); later stages read one consistent build.
select
    c.city_id,
    f.uc_id,
    f.dataset_version_id,
    'ghs_urban_centre' as territory_basis,
    f.pollutant_code,
    f.pollutant,
    f.unit,
    f.is_greenhouse_gas,
    f.is_ghg_total,
    f.edgar_sector,
    f.gpc_sector_code,
    f.gpc_sector,
    f.mapping_quality,
    f.year,
    f.value
from {{ ref('dim_city') }} as c
inner join {{ ref('fct_urban_centre_emissions') }} as f on f.uc_id = c.uc_id
