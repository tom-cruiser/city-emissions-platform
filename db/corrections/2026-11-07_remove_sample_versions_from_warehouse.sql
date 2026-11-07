-- Correction 2026-11-07: remove sample/synthetic dataset versions 352-377 from the REAL warehouse.
--
-- WHAT: 26 dataset versions loaded by `python -m ingestion load --mode sample` into
-- `warehouse` on 2026-11-07, plus their rows:
--   352        synthetic  EDGAR fixture (27 rows of INVENTED emissions)
--   353-376    sample     geoBoundaries extracts (24 files, 25 features)
--   377        sample     GHS-UCDB extract (25 polygons, 7 load_checks rows)
--
-- WHY: the command was run against the real warehouse by mistake while testing a change
-- to the "skipped" message. Sample data belongs in warehouse_test only. The real
-- warehouse must never hold invented emissions: a query that forgets to filter on
-- `origin` would report them as real. The CLI now refuses sample loads outside a
-- `*_test` database (ingestion/pipeline.py, require_test_database), so this cannot recur.
--
-- This is the one documented exception to "raw is append-only". The rows deleted are
-- copies of committed files in data/sample/, so nothing is lost.
--
-- Safe to re-run: it does nothing once applied, and aborts without changes if the rows
-- in that id range are not exactly the 26 sample/synthetic versions described above.
--
-- Run:  docker compose exec -T db psql -v ON_ERROR_STOP=1 -U pipeline -d warehouse \
--         < db/corrections/2026-11-07_remove_sample_versions_from_warehouse.sql

BEGIN;

DO $$
DECLARE
    n_versions integer;
    n_unexpected integer;
BEGIN
    IF current_database() <> 'warehouse' THEN
        RAISE EXCEPTION 'this correction is for the warehouse database, not %', current_database();
    END IF;

    SELECT count(*) INTO n_versions
    FROM raw.dataset_versions WHERE dataset_version_id BETWEEN 352 AND 377;

    IF n_versions = 0 THEN
        RAISE NOTICE 'already applied: no versions in 352-377';
        RETURN;
    END IF;

    SELECT count(*) INTO n_unexpected
    FROM raw.dataset_versions
    WHERE dataset_version_id BETWEEN 352 AND 377
      AND (origin NOT IN ('sample', 'synthetic') OR file_path NOT LIKE 'data/sample/%');

    IF n_versions <> 26 OR n_unexpected <> 0 THEN
        RAISE EXCEPTION 'expected 26 sample/synthetic versions in 352-377, found % (% unexpected); aborting',
            n_versions, n_unexpected;
    END IF;

    DELETE FROM raw.load_checks            WHERE dataset_version_id BETWEEN 352 AND 377;
    DELETE FROM raw.edgar_ucdb_emissions   WHERE dataset_version_id BETWEEN 352 AND 377;
    DELETE FROM raw.geoboundaries_features WHERE dataset_version_id BETWEEN 352 AND 377;
    DELETE FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id BETWEEN 352 AND 377;
    DELETE FROM raw.dataset_versions       WHERE dataset_version_id BETWEEN 352 AND 377;

    IF EXISTS (SELECT FROM raw.dataset_versions WHERE origin <> 'download') THEN
        RAISE EXCEPTION 'non-download versions remain in the warehouse; aborting';
    END IF;
    RAISE NOTICE 'removed % sample/synthetic versions', n_versions;
END $$;

COMMIT;
