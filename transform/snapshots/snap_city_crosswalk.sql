{#- History of the city crosswalk seed, which is edited IN PLACE (git records the edit;
    this records when it went live in this warehouse). A new row whenever a city's match
    changes: the urban centre, the boundary shape or its level, the review status, the
    note, or the official area. A city removed from the seed gets a deletion row
    (hard_deletes = new_record).

    Snapshots are the only tables that CANNOT be rebuilt from raw. Back them up before
    `docker compose down -v`: see "Snapshots" in the README.

    git_commit: the commit the run was built from, if the caller sets GIT_COMMIT
    (GIT_COMMIT=$(git rev-parse HEAD) uv run ... dbt build). Recorded, not compared. -#}
{% snapshot snap_city_crosswalk %}
{{ config(
    schema='modelled',
    unique_key='city_id',
    strategy='check',
    check_cols=['edgar_uc_id', 'gb_shape_id', 'gb_adm_level', 'gb_shape_name',
                'review_status', 'match_note', 'official_area_km2'],
    hard_deletes='new_record'
) }}
select
    *,
    '{{ env_var("GIT_COMMIT", "unknown") }}'::text as git_commit
from {{ ref('city_crosswalk') }}
{% endsnapshot %}
