-- Every urban centre in staging has a complete series in fct_urban_centre_emissions
-- (pollutants x sectors x years, all from the seeds and the data), and every city in
-- dim_city has the same complete series in fct_city_emissions. Catches dropped rows,
-- a crosswalk city missing from EDGAR, and double counting (e.g. the synthetic
-- fixture's second 'Lagos' with another ID). Returns one row per problem.
with series as (
    select
        (select count(*) from {{ ref('edgar_pollutants') }})
        * (select count(*) from {{ ref('edgar_sector_map') }})
        * (select count(distinct year) from {{ ref('fct_urban_centre_emissions') }}) as rows_per_entity
),

uc as (
    select uc_id, count(*) as n from {{ ref('fct_urban_centre_emissions') }} group by uc_id
),

city as (
    select city_id, count(*) as n from {{ ref('fct_city_emissions') }} group by city_id
)

select 'urban centre ' || uc.uc_id as entity, uc.n, s.rows_per_entity
from uc cross join series as s where uc.n <> s.rows_per_entity
union all
select 'city ' || city.city_id, city.n, s.rows_per_entity
from city cross join series as s where city.n <> s.rows_per_entity
union all
select 'urban centres in fact vs staging', (select count(*) from uc), (select count(*) from {{ ref('stg_edgar__urban_centres') }})
where (select count(*) from uc) <> (select count(*) from {{ ref('stg_edgar__urban_centres') }})
union all
select 'cities in fact vs dim_city', (select count(*) from city), (select count(*) from {{ ref('dim_city') }})
where (select count(*) from city) <> (select count(*) from {{ ref('dim_city') }})
