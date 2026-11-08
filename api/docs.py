"""OpenAPI text: the API description, tag descriptions and shared field descriptions.

The urban-centre caveat is stated here once and reused, so the docs, every emissions
field and the tests (tests/api/test_openapi.py) all say the same thing.
"""

URBAN_CENTRE_CAVEAT = (
    "Emissions of the city's GHS **urban centre**, not of its administrative boundary. "
    "EDGAR computes emissions for satellite-derived urban centres (GHS-UCDB), whose extent "
    "can differ greatly from the city's legal territory: check `uc_share_inside_admin` and the flags."
)

DESCRIPTION = f"""
Read-only access to city-level emissions, built from open data: EDGAR emissions in GHS
urban centres, GHS-UCDB urban-centre polygons, and geoBoundaries administrative boundaries.

## Read this first: urban centre ≠ city

{URBAN_CENTRE_CAVEAT}

Every response says so: `territory_basis` is always `ghs_urban_centre`, and every emissions
value is named `urban_centre_emissions`. Each city-scoped response also carries a `city`
block with:

* **`uc_share_inside_admin`**: the share of the urban centre's area inside the administrative
  boundary. Jakarta's urban centre is only ~14% inside DKI Jakarta; Paris's département 75
  covers a small part of a much larger urban centre.
* **Flags**: `low_urban_overlap` (share < 0.5: the figure describes a substantially different
  territory), `suspected_crosswalk_error` (share < 0.01: the city's match itself is probably
  wrong), `admin_area_mismatch` (the boundary polygon's area is off the official area by more
  than 25%). `flags` lists the ones that are set, plus `crosswalk_needs_review`.
* **`crosswalk_review_status`**: `needs_review` means a known problem with the city's match
  that a person still has to resolve. Such cities are included, flagged, not hidden.
* **`versions`**: the dataset versions every figure comes from. Each id is listed at
  `/v1/datasets/{{dataset_version_id}}`, with source URL, SHA-256, licence and load warnings.

## Sectors are GPC-aligned, not a GPC inventory

Emissions are published per **EDGAR sector**. Each carries a GPC-aligned sector label with a
`mapping_quality` (`direct`, `approximate`, `mixed`) and its own `sector_mapping_review_status`.
The mapping is provisional; scope 1 only; modelled top-down. Sectors are never summed into GPC
totals here, and pollutants are never added together (GHG already contains CO2), which is why
an emissions request takes exactly one pollutant.

## Numbers

Emissions and ratios are JSON numbers (IEEE-754 doubles, ~15 significant digits). The warehouse
stores emissions as exact `numeric` values as published by EDGAR; the API converts them only
when serialising. Units are given per response (`t CO2e/yr`, `t CO2/yr`, `t/yr`).

EDGAR's years are not annual (1975, 1990, 2000, 2005, 2010, 2015, 2020, 2022). Nothing is
interpolated: the trend endpoint names the previous available year and an annualised rate.

## Errors

`404` for an unknown city or dataset version, `422` for invalid parameters (FastAPI's standard
validation body), `503` when the database is unavailable. Other errors are
`{{"detail": ..., "code": ...}}`.
"""

TAGS = [
    {"name": "cities", "description": "The cities covered, their match to an urban centre and a boundary, and flags."},
    {"name": "emissions", "description": f"{URBAN_CENTRE_CAVEAT} One pollutant per request."},
    {"name": "geometry", "description": "Administrative boundary and urban centre as GeoJSON (RFC 7946), and their overlap."},
    {"name": "lineage", "description": "Dataset versions: where every figure comes from."},
    {"name": "operations", "description": "Liveness and readiness probes."},
]
