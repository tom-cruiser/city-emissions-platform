{{ config(enabled=target.name == 'test') }}
-- Test target only: the synthetic EDGAR fixture and its REVISED re-publication differ in
-- exactly the cells listed in ingestion/synthetic.py (REVISIONS). For crosswalk cities,
-- city_emission_revisions must show exactly these changes, with these factors, and nothing
-- else. The non-crosswalk urban centre's revision (ID 990002) must not appear.
-- Keep in sync with synthetic.REVISIONS: a mismatch either way fails here.
with expected (city_id, pollutant_code, edgar_sector, year, factor) as (
    values
        ('kigali-rwa', 'CO2', 'Transport', 2022, 1.25),
        ('kigali-rwa', 'GWP_100_AR5_GHG', 'Transport', 2022, 1.25),
        ('nairobi-ken', 'CO2', 'Energy', 1990, 0.8),
        ('nairobi-ken', 'GWP_100_AR5_GHG', 'Energy', 1990, 0.8),
        ('lagos-nga', 'PM2.5', 'Residential', 2015, 1.5)
),

found as (
    select * from {{ ref('city_emission_revisions') }}
)

select
    coalesce(e.city_id, f.city_id) as city_id,
    coalesce(e.pollutant_code, f.pollutant_code) as pollutant_code,
    coalesce(e.edgar_sector, f.edgar_sector) as edgar_sector,
    coalesce(e.year, f.year) as year,
    e.factor as expected_factor,
    f.to_urban_centre_emissions / nullif(f.from_urban_centre_emissions, 0) as found_factor,
    f.revision_type
from expected as e
full join found as f using (city_id, pollutant_code, edgar_sector, year)
where e.city_id is null
   or f.city_id is null
   or f.revision_type <> 'changed'
   or abs(f.to_urban_centre_emissions / f.from_urban_centre_emissions - e.factor) > 1e-6
