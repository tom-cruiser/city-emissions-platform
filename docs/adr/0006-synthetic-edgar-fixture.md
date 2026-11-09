# ADR 0006: A synthetic EDGAR fixture instead of real rows in the repo

- **Status:** Accepted; implemented in Stage 2 (`ingestion/synthetic.py`), recorded in
  Stage 8.
- **Date:** 2026-11-09 (decision taken 2026-11-06)

## Context

Tests and CI need EDGAR data offline: the real workbook is ~25 MB and CI must not touch
the network. The obvious fixture is a slice of the real file. But EDGAR's IEA-EDGAR CO2
component is licensed **CC BY-NC-ND 4.0**, and the general licence text in the file is
truncated, so it is not clear that redistributing an extract (a derivative) is allowed.
The other two sources are committed as real extracts: GHS-UCDB is CC BY 4.0, and
geoBoundaries files are committed unmodified under their per-country licences.

## Decision

Commit a **synthetic workbook with EDGAR's exact structure and invented values**:

- the same sheet names, `Units` row and 195-column header, checked against the real file,
  so the real loader reads it with no test-only code path;
- values from a seeded random generator, internally consistent (GHG ≥ CO2, nothing
  negative), byte-for-byte reproducible so regenerating creates no new dataset version;
- the real data's known problems on purpose: mis-encoded names, a duplicate
  `Lagos, Nigeria`, an urban centre outside the crosswalk, an all-zero sector;
- two re-published versions, so revisions are tested with `changed`, `removed` and
  `added` cells;
- labelled synthetic in the file name, first sheet, manifest and
  `raw.dataset_versions.origin`, and refused by any database not named `*_test`.

## Consequences

- The licence question is avoided rather than answered.
- Tests cover the loader, the modelled layer and the revisions end to end, with known
  answers that real data could not give.
- Offline runs show invented emissions, and real-data figures (for example the 12 of 25
  low-overlap cities) are checked only against a local warehouse, never in CI.

## When we would choose differently

- **A real extract** if JRC confirmed in writing that redistributing a subset is
  allowed, or if a future EDGAR release used a licence without the ND term.
- **A real extract kept outside the repo** (a private bucket that CI reads with a
  secret) if tests needed realistic magnitudes, such as checking a threshold against
  real distributions.
