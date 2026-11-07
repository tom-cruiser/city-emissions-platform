{#- Fails unless the model has as many rows as `compare_model` (optionally times `factor`). -#}
{% test row_count_matches(model, compare_model, factor=1) %}
select m.n as model_rows, c.n * {{ factor }} as expected_rows
from (select count(*) as n from {{ model }}) m, (select count(*) as n from {{ compare_model }}) c
where m.n <> c.n * {{ factor }}
{% endtest %}
