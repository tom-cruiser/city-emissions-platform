-- One row per EDGAR urban centre x emission column (current EDGAR version), unpivoted
-- from the JSON record. The unpivot and its performance notes: macros/unpivot_edgar_emissions.sql.
{{ unpivot_edgar_emissions(
    versions="select dataset_version_id from " ~ ref('stg_raw__current_versions') ~ " where source_name = 'edgar_ucdb'"
) }}
