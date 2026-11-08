-- One row per load check (dataset version x check), for the versions this target reads.
select
    l.dataset_version_id,
    l.check_name,
    l.status,
    l.detail
from {{ source('raw', 'load_checks') }} as l
inner join {{ ref('stg_raw__dataset_versions') }} as v using (dataset_version_id)
