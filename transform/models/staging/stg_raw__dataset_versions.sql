-- Every dataset version whose origin is allowed on this target (macros/raw_origins.sql),
-- current or not, flagged is_current when stg_raw__current_versions models from it.
-- Feeds reporting.dataset_versions (lineage) and the revisions models, which need the
-- older versions that staging otherwise ignores.
select
    v.dataset_version_id,
    v.source_name,
    v.source_key,
    v.origin,
    v.source_url,
    v.file_path,
    v.file_sha256,
    v.file_size_bytes,
    v.upstream_sha256,
    v.license,
    v.downloaded_at,
    v.loaded_at,
    v.row_count,
    c.dataset_version_id is not null as is_current
from {{ source('raw', 'dataset_versions') }} as v
left join {{ ref('stg_raw__current_versions') }} as c using (dataset_version_id)
where v.origin in {{ raw_origins_sql() }}
