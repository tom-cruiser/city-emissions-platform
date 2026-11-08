{#- Fails on every row whose `column_name` is null or is not the CURRENT dataset version of
    `source_name` (stg_raw__current_versions). For reporting models built from current data
    only; city_emission_revisions holds older versions by design and must not use it
    (tests/transform/test_reporting_manifest.py enforces both). -#}
{% test is_current_version(model, column_name, source_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is null
   or {{ column_name }} not in (
        select dataset_version_id
        from {{ ref('stg_raw__current_versions') }}
        where source_name = '{{ source_name }}'
   )
{% endtest %}
