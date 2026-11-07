-- Geometry repair must not drop or duplicate features: staging has exactly as many rows
-- as raw holds for the current versions.
with current_versions as (
    select dataset_version_id, source_name from {{ ref('stg_raw__current_versions') }}
),

counts as (
    select
        'ghs_ucdb' as source_name,
        (select count(*) from {{ source('raw', 'ghs_ucdb_urban_centres') }} as r
            inner join current_versions as v using (dataset_version_id)) as raw_rows,
        (select count(*) from {{ ref('stg_ghs_ucdb__urban_centres') }}) as staged_rows
    union all
    select
        'geoboundaries',
        (select count(*) from {{ source('raw', 'geoboundaries_features') }} as r
            inner join current_versions as v using (dataset_version_id)),
        (select count(*) from {{ ref('stg_geoboundaries__boundaries') }})
)

select * from counts where raw_rows <> staged_rows
