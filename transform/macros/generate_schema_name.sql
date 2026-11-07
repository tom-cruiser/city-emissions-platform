{#- Use the configured schema name as-is (modelled, reporting) instead of dbt's default
    "<target_schema>_<custom_schema>". The warehouse has exactly three fixed layer schemas. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
