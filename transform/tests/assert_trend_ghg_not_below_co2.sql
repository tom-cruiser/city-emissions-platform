-- Per city and year, the GHG total (CO2e) of the urban centre is never below its CO2:
-- the source-level rule (assert_ghg_not_below_co2) must survive summing the sectors.
select city_id, year,
       max(urban_centre_emissions) filter (where pollutant_code = 'CO2') as co2,
       max(urban_centre_emissions) filter (where is_ghg_total) as ghg
from {{ ref('city_emissions_trend') }}
where pollutant_code = 'CO2' or is_ghg_total
group by city_id, year
having max(urban_centre_emissions) filter (where is_ghg_total)
     < max(urban_centre_emissions) filter (where pollutant_code = 'CO2')
