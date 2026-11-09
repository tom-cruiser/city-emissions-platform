# ADR 0004: Content-hash dataset versions for sources, dbt snapshots for edited seeds

- **Status:** Accepted; versions implemented in Stage 2 (`ingestion/versioning.py`),
  snapshots and revisions in Stage 4. Recorded in Stage 8.
- **Date:** 2026-11-09 (decisions taken 2026-11-05 and 2026-11-08)

## Context

Two kinds of input change over time, in different ways:

- **Source files** (EDGAR, GHS-UCDB, geoBoundaries) are published by others. A new
  release, or a silent fix under the same file name, must not overwrite what was loaded
  before, and every published figure must trace back to the exact bytes it came from.
- **Two seeds are edited in place** in this repo: the city crosswalk and the EDGAR → GPC
  sector map. Changing either relabels figures without any new source file.

## Decision

1. **Sources: the SHA-256 of the file is the version.** Each loaded file gets a row in
   `raw.dataset_versions` (URL, hash, size, licence, download and load times), and every
   raw row carries its `dataset_version_id`. `(source_name, source_key, file_sha256)` is
   unique and registration is `INSERT … ON CONFLICT DO NOTHING`, so the same bytes are a
   no-op and changed bytes are a new version. `raw` is append-only.
2. **Revisions are computed by comparing versions** (`city_emission_revisions`), not by
   snapshotting emissions. Any two loaded versions can be compared at any time.
3. **Seeds: dbt snapshots** (`snap_city_crosswalk`, `snap_edgar_sector_map`, `check`
   strategy, `hard_deletes = new_record`) record when each change went live in this
   warehouse, with the git commit of the build. Git records who changed what and why.
4. **Snapshot tables are backed up with `pg_dump`**, because they are the only tables
   that cannot be rebuilt.

## Consequences

- Idempotency and lineage come from one mechanism, and every API response carries version
  ids that resolve at `/v1/datasets/{id}`.
- Every version stays in `raw`. EDGAR is about 25 MB per release, so this costs little.
- Snapshot history is lost with the volume unless the manual backup was run. Automating
  it before each Dagster build is listed as a next step.

## When we would choose differently

- **Snapshots on sources** if a source were a mutable API or table with no files to
  hash, since then there is nothing to version by content.
- **Incremental models or a lakehouse format** (Delta, Iceberg time travel) if raw grew
  too large to keep every version or to rebuild from in one run.
- **Seed history in a reviewed table with its own audit log** (instead of seeds plus
  snapshots) if non-developers edited the crosswalk through a UI.
