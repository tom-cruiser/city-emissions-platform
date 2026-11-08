-- Every reporting model that carries a city's overlap flags and review status carries the
-- same values as city_overlap. One row per disagreeing (model, city).
{% set carriers = ['cities', 'city_emissions', 'city_emissions_trend'] %}
{% for m in carriers %}
select distinct '{{ m }}' as model, x.city_id
from {{ ref(m) }} as x
inner join {{ ref('city_overlap') }} as o using (city_id)
where (x.uc_share_inside_admin, x.low_urban_overlap, x.suspected_crosswalk_error, x.crosswalk_review_status)
      is distinct from
      (o.uc_share_inside_admin, o.low_urban_overlap, o.suspected_crosswalk_error, o.crosswalk_review_status)
{% if not loop.last %}union all{% endif %}
{% endfor %}
