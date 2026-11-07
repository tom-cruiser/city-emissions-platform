-- Every source the models need has a current version: exactly one EDGAR file, exactly
-- one GHS-UCDB file, and one geoBoundaries file per (country, ADM level) in the crosswalk.
-- Returns one row per problem.
with needed as (
    select 'edgar_ucdb' as source_name, null::text as source_key, 1 as expected
    union all
    select 'ghs_ucdb', null, 1
    union all
    select distinct 'geoboundaries', country_iso3 || '_' || gb_adm_level, 1
    from {{ ref('city_crosswalk') }}
),

found as (
    select n.source_name, n.source_key, n.expected, count(v.dataset_version_id) as found
    from needed as n
    left join {{ ref('stg_raw__current_versions') }} as v
        on v.source_name = n.source_name
        and (n.source_key is null or v.source_key = n.source_key)
    group by n.source_name, n.source_key, n.expected
)

select * from found where found <> expected
