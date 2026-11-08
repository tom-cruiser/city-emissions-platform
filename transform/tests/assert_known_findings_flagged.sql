-- The crosswalk problems documented in the README (checked 2026-11-07) are flagged:
--   Accra: 0.5% of the urban centre inside a boundary ~28% of the official area
--          -> suspected_crosswalk_error and admin_area_mismatch
--   Buenos Aires: boundary 948 km2 against an official 200 km2 -> admin_area_mismatch
-- When either is fixed in the crosswalk, this test fails ON PURPOSE: update it together
-- with the README, so a flag never disappears silently.
with expected (city_id, flag) as (
    values
        ('accra-gha', 'suspected_crosswalk_error'),
        ('accra-gha', 'admin_area_mismatch'),
        ('buenos-aires-arg', 'admin_area_mismatch')
)

select e.*
from expected as e
left join {{ ref('city_overlap') }} as o using (city_id)
where o.city_id is null or not (e.flag = any(o.flags))
