-- The current (not deleted) snapshot rows are exactly the seeds, on every tracked column:
-- a key in only one of them, or a tracked value that differs, is one row each. Proves the
-- snapshot ran after the seed and tracks the columns it claims to.
{% set tracked = {
    'snap_city_crosswalk': ('city_crosswalk', 'city_id',
        ['edgar_uc_id', 'gb_shape_id', 'gb_adm_level', 'gb_shape_name', 'review_status', 'match_note', 'official_area_km2']),
    'snap_edgar_sector_map': ('edgar_sector_map', 'edgar_sector',
        ['gpc_sector_code', 'gpc_sector', 'mapping_quality', 'review_status', 'note']),
} %}
{% for snap, (seed, key, cols) in tracked.items() %}
select '{{ snap }}' as snapshot, coalesce(s.{{ key }}, t.{{ key }})::text as key
from (
    select * from {{ ref(snap) }}
    where dbt_valid_to is null and coalesce(dbt_is_deleted, 'False') <> 'True'
) as s
full join {{ ref(seed) }} as t using ({{ key }})
where s.{{ key }} is null or t.{{ key }} is null
   or ({% for c in cols %}s.{{ c }}{% if not loop.last %}, {% endif %}{% endfor %})
      is distinct from
      ({% for c in cols %}t.{{ c }}{% if not loop.last %}, {% endif %}{% endfor %})
{% if not loop.last %}union all{% endif %}
{% endfor %}
