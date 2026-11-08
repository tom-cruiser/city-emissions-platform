-- Grain: one row per crosswalk city x EDGAR dataset version x pollutant x EDGAR sector x
-- year: EVERY EDGAR version this target may read, current or not. Source data is
-- versioned in raw (append-only, one dataset_version_id per file), so revisions are
-- modelled by comparing versions, not with a snapshot (README "Snapshots").
-- Table: read by city_emission_revisions and its tests. 25 cities x 192 cells x versions.
select
    c.city_id,
    e.uc_id,
    e.dataset_version_id,
    v.loaded_at as version_loaded_at,
    v.is_current as version_is_current,
    e.pollutant_code,
    p.pollutant,
    p.unit,
    p.is_ghg_total,
    e.edgar_sector,
    e.year,
    e.value
from {{ ref('stg_edgar__crosswalk_emissions_by_version') }} as e
inner join {{ ref('city_crosswalk') }} as c on c.edgar_uc_id = e.uc_id
inner join {{ ref('stg_raw__dataset_versions') }} as v using (dataset_version_id)
left join {{ ref('edgar_pollutants') }} as p using (pollutant_code)
