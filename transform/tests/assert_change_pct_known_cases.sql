-- macros/change_pct.sql on hand-computed cases. Returns one row per wrong answer.
with cases (label, curr, prev, years, expected_change, expected_annualised) as (
    values
        ('+21% over 2 years = +10%/yr', 121.0, 100.0, 2, 21.0, 10.0),
        ('halved in 1 year', 50.0, 100.0, 1, -50.0, -50.0),
        ('unchanged over 15 years', 100.0, 100.0, 15, 0.0, 0.0),
        ('doubled over 10 years', 200.0, 100.0, 10, 100.0, 7.177346253629313),
        ('fell to zero', 0.0, 100.0, 5, -100.0, -100.0),
        ('from zero: no ratio', 10.0, 0.0, 5, null, null),
        ('no previous point', 10.0, null, null, null, null)
),

computed as (
    select
        *,
        {{ change_pct('curr', 'prev') }} as change,
        {{ annualised_change_pct('curr', 'prev', 'years') }} as annualised
    from cases
)

select *
from computed
where not (
    (change is null and expected_change is null) or abs(change - expected_change) < 1e-9
) or not (
    (annualised is null and expected_annualised is null) or abs(annualised - expected_annualised) < 1e-9
)
