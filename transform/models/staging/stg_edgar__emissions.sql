-- One row per EDGAR urban centre x emission column (current EDGAR version), unpivoted
-- from the JSON record. Column names are EMI_<pollutant>_<sector>_<year>; the pollutant
-- may itself contain underscores (GWP_100_AR5_GHG), the sector and year cannot.
-- A column that does not parse gives null parts, which the not_null tests reject.
--
-- Two performance traps, each worth minutes on the full file (11,686 x 192 cells):
-- 1. Each record is a ~2.5 KB compressed (TOASTed) jsonb. Written next to the
--    jsonb_each_text() call, `record ->> 'ID_UC_G0'` is evaluated once per OUTPUT row and
--    decompresses the record 2.24M times. `offset 0` stops Postgres flattening the
--    subquery, so the ID is read once per record (33 s -> 1.4 s).
-- 2. The regex backtracks on its greedy (.+) at ~12 us a match, so it runs once per
--    distinct column name (192) and is joined back, not once per cell. That needs a
--    fence too: a flattened subquery's expressions are evaluated in the join's output.
with versions as (
    select dataset_version_id
    from {{ ref('stg_raw__current_versions') }}
    where source_name = 'edgar_ucdb'
),

records as (
    select
        e.dataset_version_id,
        (e.record ->> 'ID_UC_G0')::integer as uc_id,
        e.source_unit,
        e.record
    from {{ source('raw', 'edgar_ucdb_emissions') }} as e
    inner join versions using (dataset_version_id)
    offset 0  -- optimisation fence, see 1. above
),

source_columns as (
    select
        source_column,
        regexp_match(source_column, '^EMI_(.+)_([A-Za-z]+)_([0-9]{4})$') as parts
    from (select distinct jsonb_object_keys(record) as source_column from records) as k
    where source_column like 'EMI\_%'
    offset 0  -- fence: otherwise the planner moves regexp_match into the join's output, once per cell
)

select
    r.dataset_version_id,
    r.uc_id,
    r.source_unit,
    kv.key as source_column,
    c.parts[1] as pollutant_code,
    c.parts[2] as edgar_sector,
    c.parts[3]::integer as year,
    kv.value::numeric as value
from records as r
cross join lateral jsonb_each_text(r.record) as kv (key, value)
inner join source_columns as c on c.source_column = kv.key
