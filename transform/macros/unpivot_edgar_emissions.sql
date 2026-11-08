{#- One row per EDGAR urban centre x emission column, unpivoted from raw's JSON records.
    Column names are EMI_<pollutant>_<sector>_<year>; the pollutant may itself contain
    underscores (GWP_100_AR5_GHG), the sector and year cannot. A column that does not parse
    gives null parts, which the not_null tests reject.

    versions: SQL selecting the dataset_version_id(s) to read.
    uc_ids:   optional SQL selecting the urban-centre IDs to keep (filtered BEFORE the
              unpivot, so reading every version for 25 cities stays cheap).

    Used by stg_edgar__emissions (current version, every urban centre) and
    stg_edgar__crosswalk_emissions_by_version (every version, crosswalk cities).

    Two performance traps, each worth minutes on the full file (11,686 x 192 cells):
    1. Each record is a ~2.5 KB compressed (TOASTed) jsonb. Written next to the
       jsonb_each_text() call, `record ->> 'ID_UC_G0'` is evaluated once per OUTPUT row and
       decompresses the record 2.24M times. `offset 0` stops Postgres flattening the
       subquery, so the ID is read once per record (33 s -> 1.4 s).
    2. The regex backtracks on its greedy (.+) at ~12 us a match, so it runs once per
       distinct column name (192) and is joined back, not once per cell. That needs a
       fence too: a flattened subquery's expressions are evaluated in the join's output. -#}
{% macro unpivot_edgar_emissions(versions, uc_ids=none) %}
with records as (
    select
        e.dataset_version_id,
        (e.record ->> 'ID_UC_G0')::integer as uc_id,
        e.source_unit,
        e.record
    from {{ source('raw', 'edgar_ucdb_emissions') }} as e
    where e.dataset_version_id in ({{ versions }})
    {%- if uc_ids is not none %}
      and (e.record ->> 'ID_UC_G0')::integer in ({{ uc_ids }})
    {%- endif %}
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
{% endmacro %}
