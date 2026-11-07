-- Total GHG in CO2e can never be below CO2 alone, per urban centre, sector and year
-- (other gases only add). True for every cell of EDGAR v2024 (0 of 560,928) and built
-- into the synthetic fixture, so a failure means a broken unpivot or a broken source.
select uc_id, edgar_sector, year,
       max(value) filter (where pollutant_code = 'CO2') as co2,
       max(value) filter (where is_ghg_total) as ghg
from {{ ref('fct_urban_centre_emissions') }}
where pollutant_code = 'CO2' or is_ghg_total
group by uc_id, edgar_sector, year
having max(value) filter (where is_ghg_total) < max(value) filter (where pollutant_code = 'CO2')
