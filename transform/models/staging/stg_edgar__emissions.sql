-- One row per EDGAR urban centre x emission column (current EDGAR version), unpivoted
-- from the JSON record. Column names are EMI_<pollutant>_<sector>_<year>; the pollutant
-- may itself contain underscores (GWP_100_AR5_GHG), the sector and year cannot.
-- A column that does not parse gives null parts, which the not_null tests reject.
with versions as (
    select dataset_version_id
    from {{ ref('stg_raw__current_versions') }}
    where source_name = 'edgar_ucdb'
)

select
    e.dataset_version_id,
    (e.record ->> 'ID_UC_G0')::integer as uc_id,
    e.source_unit,
    kv.key as source_column,
    parsed.parts[1] as pollutant_code,
    parsed.parts[2] as edgar_sector,
    parsed.parts[3]::integer as year,
    kv.value::numeric as value
from {{ source('raw', 'edgar_ucdb_emissions') }} as e
inner join versions using (dataset_version_id)
cross join lateral jsonb_each_text(e.record) as kv (key, value)
cross join lateral (
    select regexp_match(kv.key, '^EMI_(.+)_([A-Za-z]+)_([0-9]{4})$') as parts
) as parsed
where kv.key like 'EMI\_%'
