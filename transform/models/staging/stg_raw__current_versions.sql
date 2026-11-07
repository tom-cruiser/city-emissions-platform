-- The dataset version each source file is currently modelled from: per (source_name,
-- source_key), the most recently loaded version whose origin is allowed on this target
-- (macros/raw_origins.sql). Every staging model joins through here, so the modelled layer
-- reads exactly one version of each source file.
select distinct on (source_name, source_key)
    dataset_version_id,
    source_name,
    source_key,
    origin,
    source_url,
    file_sha256,
    license,
    downloaded_at,
    loaded_at,
    row_count
from {{ source('raw', 'dataset_versions') }}
where origin in {{ raw_origins_sql() }}
order by source_name, source_key, loaded_at desc, dataset_version_id desc
