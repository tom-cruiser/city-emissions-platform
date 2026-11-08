{{ config(enabled=target.name == 'test') }}
-- Test target only. The synthetic EDGAR fixture is loaded as three versions of v2024
-- (ingestion/synthetic.py, VARIANTS), and for crosswalk cities city_emission_revisions must
-- show exactly this, and nothing else:
--   original -> revised   'changed': the five REVISIONS cells, with their factors
--                         'removed': every cell of Dakar (its row is missing)
--   revised  -> restored  'added':   every cell of Dakar, values equal to what was removed
-- The ×2 change to the non-crosswalk urban centre (990002) must not appear.
-- Keep in sync with synthetic.REVISIONS / REMOVED_UC_ID: a mismatch either way fails here.
-- One row per problem.
with files as (
    select dataset_version_id, regexp_replace(file_path, '^.*/', '') as file
    from {{ ref('stg_raw__dataset_versions') }}
    where source_name = 'edgar_ucdb'
),

found as (
    select r.*, ff.file as from_file, tf.file as to_file
    from {{ ref('city_emission_revisions') }} as r
    inner join files as ff on ff.dataset_version_id = r.from_edgar_version_id
    inner join files as tf on tf.dataset_version_id = r.to_edgar_version_id
),

dakar_cells as (
    select count(*) as n from {{ ref('fct_city_emissions') }} where city_id = 'dakar-sen'
),

expected_changed (city_id, pollutant_code, edgar_sector, year, factor) as (
    values
        ('kigali-rwa', 'CO2', 'Transport', 2022, 1.25),
        ('kigali-rwa', 'GWP_100_AR5_GHG', 'Transport', 2022, 1.25),
        ('nairobi-ken', 'CO2', 'Energy', 1990, 0.8),
        ('nairobi-ken', 'GWP_100_AR5_GHG', 'Energy', 1990, 0.8),
        ('lagos-nga', 'PM2.5', 'Residential', 2015, 1.5)
),

changed as (
    select * from found where revision_type = 'changed'
)

-- changed: exactly the expected cells, original -> revised, with their factors
select 'changed ' || coalesce(e.city_id, c.city_id) || ' ' || coalesce(e.pollutant_code, c.pollutant_code)
       || ' ' || coalesce(e.edgar_sector, c.edgar_sector) || ' ' || coalesce(e.year, c.year) as problem
from expected_changed as e
full join changed as c using (city_id, pollutant_code, edgar_sector, year)
where e.city_id is null
   or c.city_id is null
   or c.from_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC.xlsx'
   or c.to_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC_REVISED.xlsx'
   or abs(c.to_urban_centre_emissions / c.from_urban_centre_emissions - e.factor) > 1e-6

union all
-- removed: only Dakar, only original -> revised, every one of its cells
select 'removed row outside Dakar or on the wrong pair: ' || city_id || ' ' || from_file
from found
where revision_type = 'removed'
  and (city_id <> 'dakar-sen'
       or from_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC.xlsx'
       or to_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC_REVISED.xlsx')
union all
select 'removed: ' || count(*) || ' cells, expected ' || max(d.n)
from found cross join dakar_cells as d
where revision_type = 'removed'
having count(*) <> max(d.n) or count(*) = 0

union all
-- added: only Dakar, only revised -> restored, every one of its cells
select 'added row outside Dakar or on the wrong pair: ' || city_id || ' ' || from_file
from found
where revision_type = 'added'
  and (city_id <> 'dakar-sen'
       or from_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC_REVISED.xlsx'
       or to_file <> 'EDGAR_emiss_on_UCDB_2024_SYNTHETIC_REVISED_2.xlsx')
union all
select 'added: ' || count(*) || ' cells, expected ' || max(d.n)
from found cross join dakar_cells as d
where revision_type = 'added'
having count(*) <> max(d.n) or count(*) = 0

union all
-- what came back is what went away, cell for cell
select 'added value differs from removed value: ' || a.pollutant_code || ' ' || a.edgar_sector || ' ' || a.year
from (select * from found where revision_type = 'added') as a
left join (select * from found where revision_type = 'removed') as r
    using (city_id, pollutant_code, edgar_sector, year)
where r.from_urban_centre_emissions is distinct from a.to_urban_centre_emissions
