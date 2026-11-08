-- Grain: one row per dataset version this target is allowed to read (downloads on the
-- warehouse; sample/synthetic on warehouse_test), current or not. Serves GET /datasets:
-- the lineage every *_version_id column in reporting points at.
-- Load-check warnings are copied here because the API cannot read raw.load_checks.
with versions as (
    select * from {{ ref('stg_raw__dataset_versions') }}
),

warnings as (
    select dataset_version_id, array_agg(check_name order by check_name) as load_check_warnings
    from {{ ref('stg_raw__load_checks') }}
    where status = 'warn'
    group by dataset_version_id
)

select
    v.dataset_version_id::bigint as dataset_version_id,
    v.source_name::text as source_name,
    v.source_key::text as source_key,
    v.origin::text as origin,
    v.is_current::boolean as is_current,
    v.source_url::text as source_url,
    v.file_sha256::character(64) as file_sha256,
    v.upstream_sha256::character(64) as upstream_sha256,
    v.file_size_bytes::bigint as file_size_bytes,
    v.license::text as license,
    v.downloaded_at::timestamptz as downloaded_at,
    v.loaded_at::timestamptz as loaded_at,
    v.row_count::integer as row_count,
    coalesce(w.load_check_warnings, '{}')::text[] as load_check_warnings
from versions as v
left join warnings as w using (dataset_version_id)
