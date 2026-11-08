{#- Percentage changes between two points of a series that is NOT annual (EDGAR has 1975,
    1990, 2000, 2005, ... 2020, 2022), so a raw change over 15 years and one over 2 years
    are not comparable. Tested with known answers in tests/assert_change_pct_known_cases.sql.

    change_pct:            (curr / prev - 1) * 100
    annualised_change_pct: compound annual rate, ((curr / prev) ^ (1 / years) - 1) * 100
    Both are null when there is no previous point or prev = 0 (no meaningful ratio).
    curr = 0 gives -100. -#}
{% macro change_pct(curr, prev) -%}
    (({{ curr }})::double precision / nullif(({{ prev }})::double precision, 0) - 1) * 100
{%- endmacro %}

{% macro annualised_change_pct(curr, prev, years) -%}
    (power(({{ curr }})::double precision / nullif(({{ prev }})::double precision, 0),
           1.0 / nullif({{ years }}, 0)) - 1) * 100
{%- endmacro %}
