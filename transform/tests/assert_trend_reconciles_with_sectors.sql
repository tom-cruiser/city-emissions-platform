-- city_emissions_trend is exactly the sum of city_emissions over every EDGAR sector in the
-- sector map: same totals, one sector count, and no (city, pollutant, year) on one side
-- only. Returns one row per mismatch.
with sectors as (
    select count(*) as n from {{ ref('edgar_sector_map') }}
),

summed as (
    select city_id, pollutant_code, year,
           sum(urban_centre_emissions) as total, count(*) as sector_count
    from {{ ref('city_emissions') }}
    group by city_id, pollutant_code, year
)

select
    coalesce(s.city_id, t.city_id) as city_id,
    coalesce(s.pollutant_code, t.pollutant_code) as pollutant_code,
    coalesce(s.year, t.year) as year,
    s.total as summed_total,
    t.urban_centre_emissions as trend_total,
    t.sector_count
from summed as s
full join {{ ref('city_emissions_trend') }} as t using (city_id, pollutant_code, year)
cross join sectors
where s.city_id is null
   or t.city_id is null
   or s.total <> t.urban_centre_emissions
   or t.sector_count <> sectors.n
