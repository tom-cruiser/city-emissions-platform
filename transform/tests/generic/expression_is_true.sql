{#- Fails on every row where `expression` is not true (false OR null). -#}
{% test expression_is_true(model, expression, column_name=None) %}
select * from {{ model }} where ({{ expression }}) is not true
{% endtest %}
