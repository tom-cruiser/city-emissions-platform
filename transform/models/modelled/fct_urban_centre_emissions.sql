{{ config(indexes=[{'columns': ['uc_id']}]) }}
-- Grain: one row per EDGAR urban centre x pollutant x EDGAR sector x year, for the
-- CURRENT EDGAR version only (dataset_version_id is the same on every row).
-- All 11,686 urban centres, not only the crosswalk cities, so the source-quality tests
-- (no negatives, GHG >= CO2, complete series) cover the whole file.
-- Values stay in the source's tonnes per year; `unit` comes from the pollutant seed.
-- Pollutants are never added together (GHG already contains CO2).
-- Left joins to the seeds: an unknown pollutant or sector gives nulls, which tests reject.
select
    e.dataset_version_id,
    e.uc_id,
    e.pollutant_code,
    p.pollutant,
    p.unit,
    p.is_greenhouse_gas,
    p.is_ghg_total,
    e.edgar_sector,
    s.gpc_sector_code,
    s.gpc_sector,
    s.mapping_quality,
    e.year,
    e.value
from {{ ref('stg_edgar__emissions') }} as e
left join {{ ref('edgar_pollutants') }} as p using (pollutant_code)
left join {{ ref('edgar_sector_map') }} as s using (edgar_sector)
