-- The current-version slice of fct_city_emissions_by_version is exactly fct_city_emissions:
-- same cells, same values. Both come from macros/unpivot_edgar_emissions.sql by different
-- routes (every urban centre of the current version, vs crosswalk cities of every
-- version), so this ties the revisions models to what reporting serves. One row per difference.
with by_version as (
    select city_id, dataset_version_id, pollutant_code, edgar_sector, year, value
    from {{ ref('fct_city_emissions_by_version') }}
    where version_is_current
),

current_fact as (
    select city_id, dataset_version_id, pollutant_code, edgar_sector, year, value
    from {{ ref('fct_city_emissions') }}
)

select * from (select * from by_version except select * from current_fact) as only_by_version
union all
select * from (select * from current_fact except select * from by_version) as only_fact
