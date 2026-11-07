{#- Fails unless `column_name` has exactly `expected` distinct non-null values. -#}
{% test distinct_count(model, column_name, expected) %}
select count(distinct {{ column_name }}) as n
from {{ model }}
having count(distinct {{ column_name }}) <> {{ expected }}
{% endtest %}
