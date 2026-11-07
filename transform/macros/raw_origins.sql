{#- Which raw.dataset_versions.origin values staging reads.

    Default: ['download'] on the real warehouse, ['sample', 'synthetic'] on the test target.
    Override with --vars '{raw_origins: [...]}'.

    Mirrors the ingestion guard (ingestion/versioning.py): sample or synthetic data may
    only be read in a database named *_test, so the synthetic EDGAR fixture's invented
    emissions can never be modelled as real ones. -#}
{% macro raw_origins() -%}
    {%- set default = ['sample', 'synthetic'] if target.name == 'test' else ['download'] -%}
    {%- set origins = var('raw_origins', default) -%}
    {%- set non_download = origins | reject('equalto', 'download') | list -%}
    {%- if non_download and not target.dbname.endswith('_test') -%}
        {{ exceptions.raise_compiler_error(
            "raw_origins " ~ non_download ~ " may only be used on a *_test database, not " ~ target.dbname) }}
    {%- endif -%}
    {{ return(origins) }}
{%- endmacro %}

{% macro raw_origins_sql() -%}
    ({%- for o in raw_origins() -%}'{{ o }}'{%- if not loop.last %}, {% endif -%}{%- endfor -%})
{%- endmacro %}
