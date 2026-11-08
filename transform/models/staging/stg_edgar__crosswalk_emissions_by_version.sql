-- One row per crosswalk urban centre x emission column x EDGAR dataset version: EVERY
-- version this target may read, not only the current one. Feeds the revisions models.
-- Filtered to the crosswalk's urban centres before the unpivot (25 of 11,686 records per
-- version), so reading all versions stays cheap.
{{ unpivot_edgar_emissions(
    versions="select dataset_version_id from " ~ ref('stg_raw__dataset_versions') ~ " where source_name = 'edgar_ucdb'",
    uc_ids="select edgar_uc_id from " ~ ref('city_crosswalk')
) }}
