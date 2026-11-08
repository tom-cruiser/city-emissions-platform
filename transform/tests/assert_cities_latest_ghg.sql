-- cities.latest_urban_centre_ghg_t_co2e is the GHG total of the city's last year in
-- city_emissions_trend, and that pollutant really is in t CO2e. One row per mismatch.
with latest as (
    select distinct on (city_id) city_id, year, urban_centre_emissions, unit
    from {{ ref('city_emissions_trend') }}
    where is_ghg_total
    order by city_id, year desc
)

select c.city_id, c.last_year, l.year, c.latest_urban_centre_ghg_t_co2e, l.urban_centre_emissions, l.unit
from {{ ref('cities') }} as c
left join latest as l using (city_id)
where l.city_id is null
   or c.last_year <> l.year
   or c.latest_urban_centre_ghg_t_co2e <> l.urban_centre_emissions
   or l.unit <> 't CO2e/yr'
