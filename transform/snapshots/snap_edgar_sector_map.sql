{#- History of the EDGAR -> GPC sector map seed (ADR 0002), edited IN PLACE while the
    mapping awaits specialist review. A change here relabels every reported figure without
    changing edgar_version_id, so comparing dataset versions cannot see it; this can.
    Same rules as snap_city_crosswalk (backups, git_commit, deletions). -#}
{% snapshot snap_edgar_sector_map %}
{{ config(
    schema='modelled',
    unique_key='edgar_sector',
    strategy='check',
    check_cols=['gpc_sector_code', 'gpc_sector', 'mapping_quality', 'review_status', 'note'],
    hard_deletes='new_record'
) }}
select
    *,
    '{{ env_var("GIT_COMMIT", "unknown") }}'::text as git_commit
from {{ ref('edgar_sector_map') }}
{% endsnapshot %}
