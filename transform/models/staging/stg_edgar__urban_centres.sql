-- One row per EDGAR urban centre (current EDGAR version): ID and repaired names.
-- EDGAR's names are double-encoded (macros/repair_mojibake.sql); the source text is kept.
with versions as (
    select dataset_version_id
    from {{ ref('stg_raw__current_versions') }}
    where source_name = 'edgar_ucdb'
),

rows as (
    select
        e.dataset_version_id,
        e.source_row_number,
        (e.record ->> 'ID_UC_G0')::integer as uc_id,
        e.record ->> 'UC_name' as uc_name_source,
        e.record ->> 'UC_country' as country_name_source
    from {{ source('raw', 'edgar_ucdb_emissions') }} as e
    inner join versions using (dataset_version_id)
)

select
    dataset_version_id,
    source_row_number,
    uc_id,
    {{ repair_mojibake('uc_name_source') }} as uc_name,
    {{ repair_mojibake('country_name_source') }} as country_name,
    uc_name_source,
    country_name_source,
    (uc_name_source ~ '[^\x01-\x7f]' or country_name_source ~ '[^\x01-\x7f]') as name_repaired,
    -- '?' replaced characters upstream; they cannot be recovered (e.g. 'Bia?ystok').
    (strpos(uc_name_source, '?') > 0 or strpos(country_name_source, '?') > 0) as name_lossy
from rows
