-- Grain: one row per city x pollutant x EDGAR sector x year x pair of CONSECUTIVE EDGAR
-- versions (ordered by load time), only where the value changed, appeared or disappeared.
-- Serves GET /cities/{id}/revisions. Holds OLDER versions by design, so its from/to version
-- columns are tested against dataset_versions but NOT against the current version.
-- Figures are the emissions of the city's GHS URBAN CENTRE, like everywhere in reporting;
-- the overlap flags carried are today's (current GHS-UCDB and boundary versions).
-- Versions are paired across source_key too, so a new EDGAR release (v2025) would be
-- compared with the last v2024 file.
-- On the real warehouse this is empty until a second EDGAR version is loaded.
with versions as (
    select
        dataset_version_id,
        lead(dataset_version_id) over (order by loaded_at, dataset_version_id) as next_version_id
    from {{ ref('stg_raw__dataset_versions') }}
    where source_name = 'edgar_ucdb'
),

pairs as (
    select dataset_version_id as from_version_id, next_version_id as to_version_id
    from versions
    where next_version_id is not null
),

cells as (
    select * from {{ ref('fct_city_emissions_by_version') }}
),

from_cells as (
    select p.from_version_id, p.to_version_id, c.*
    from pairs as p
    inner join cells as c on c.dataset_version_id = p.from_version_id
),

to_cells as (
    select p.from_version_id, p.to_version_id, c.*
    from pairs as p
    inner join cells as c on c.dataset_version_id = p.to_version_id
),

compared as (
    select
        coalesce(t.city_id, f.city_id) as city_id,
        coalesce(t.uc_id, f.uc_id) as uc_id,
        coalesce(t.pollutant_code, f.pollutant_code) as pollutant_code,
        coalesce(t.edgar_sector, f.edgar_sector) as edgar_sector,
        coalesce(t.year, f.year) as year,
        coalesce(t.pollutant, f.pollutant) as pollutant,
        coalesce(t.unit, f.unit) as unit,
        coalesce(t.is_ghg_total, f.is_ghg_total) as is_ghg_total,
        coalesce(t.from_version_id, f.from_version_id) as from_version_id,
        coalesce(t.to_version_id, f.to_version_id) as to_version_id,
        f.value as from_value,
        t.value as to_value
    from from_cells as f
    full join to_cells as t
        on t.from_version_id = f.from_version_id
        and t.to_version_id = f.to_version_id
        and t.city_id = f.city_id
        and t.pollutant_code = f.pollutant_code
        and t.edgar_sector = f.edgar_sector
        and t.year = f.year
)

select
    r.city_id::text as city_id,
    r.pollutant_code::text as pollutant_code,
    r.edgar_sector::text as edgar_sector,
    r.year::integer as year,
    r.from_version_id::bigint as from_edgar_version_id,
    r.to_version_id::bigint as to_edgar_version_id,
    (case
        when r.from_value is null then 'added'
        when r.to_value is null then 'removed'
        else 'changed'
    end)::text as revision_type,
    'ghs_urban_centre'::text as territory_basis,
    r.from_value::numeric as from_urban_centre_emissions,
    r.to_value::numeric as to_urban_centre_emissions,
    (r.to_value - r.from_value)::numeric as change,
    {{ change_pct('r.to_value', 'r.from_value') }} as change_pct,
    r.pollutant::text as pollutant,
    r.unit::text as unit,
    r.is_ghg_total::boolean as is_ghg_total,
    r.uc_id::integer as uc_id,
    o.uc_share_inside_admin,
    o.low_urban_overlap,
    o.suspected_crosswalk_error,
    o.crosswalk_review_status,
    o.ucdb_version_id,
    o.gb_version_id
from compared as r
inner join {{ ref('city_overlap') }} as o using (city_id)
where r.from_value is distinct from r.to_value
