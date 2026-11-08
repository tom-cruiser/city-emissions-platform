"""Response models and query enums. Field descriptions mirror the reporting layer's
(transform/models/reporting/_reporting.yml). Values are validated on the way out, so a
response can never silently drift from these models."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.docs import URBAN_CENTRE_CAVEAT

# --- Query enums. tests/api/test_enums.py checks each against the values in reporting. ---


class Pollutant(StrEnum):
    GHG = "GHG"
    CO2 = "CO2"
    NOx = "NOx"
    PM2_5 = "PM2.5"


class EdgarSector(StrEnum):
    Agriculture = "Agriculture"
    Energy = "Energy"
    Industry = "Industry"
    Residential = "Residential"
    Transport = "Transport"
    Waste = "Waste"


class ReviewStatus(StrEnum):
    accepted = "accepted"
    needs_review = "needs_review"


class Flag(StrEnum):
    low_urban_overlap = "low_urban_overlap"
    suspected_crosswalk_error = "suspected_crosswalk_error"
    admin_area_mismatch = "admin_area_mismatch"
    crosswalk_needs_review = "crosswalk_needs_review"


class RevisionType(StrEnum):
    changed = "changed"
    added = "added"
    removed = "removed"


class SourceName(StrEnum):
    edgar_ucdb = "edgar_ucdb"
    ghs_ucdb = "ghs_ucdb"
    geoboundaries = "geoboundaries"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


UrbanCentreEmissions = Field(description=URBAN_CENTRE_CAVEAT + " In `unit`.")

# --- The block every city-scoped response carries ---


class Versions(_Model):
    """Dataset versions the response's figures come from (see /v1/datasets/{id})."""

    edgar: int | None = Field(description="EDGAR emissions version. Null only where no EDGAR figure is involved.")
    ghs_ucdb: int = Field(description="GHS-UCDB urban-centre polygons version.")
    geoboundaries: int = Field(description="geoBoundaries version (one country file) of the boundary.")


class CityContext(_Model):
    """Who the figures are about, on what territory, and how much to trust the match."""

    city_id: str = Field(examples=["accra-gha"])
    city_name: str
    country_iso3: str
    territory_basis: Literal["ghs_urban_centre"] = Field(
        description="Always `ghs_urban_centre`: " + URBAN_CENTRE_CAVEAT)
    uc_share_inside_admin: float = Field(
        description="Share (0-1) of the urban centre's area inside the administrative boundary.")
    low_urban_overlap: bool = Field(
        description="uc_share_inside_admin < 0.5: the figures describe a substantially different territory.")
    suspected_crosswalk_error: bool = Field(
        description="uc_share_inside_admin < 0.01: the city's match itself is probably wrong.")
    admin_area_mismatch: bool = Field(
        description="The boundary polygon's area differs from the official area by more than 25%.")
    crosswalk_review_status: ReviewStatus = Field(
        description="`needs_review`: a known problem with the city's match that a person must resolve.")
    flags: list[Flag] = Field(description="The flags that are set. Empty when none is.")
    versions: Versions


class CitySummary(CityContext):
    uc_id: int = Field(description="GHS urban-centre ID (ID_UC_G0), the same in EDGAR and GHS-UCDB.")
    edgar_uc_name: str | None
    gb_adm_level: str | None
    gb_shape_name: str | None
    match_note: str | None = Field(description="Why this unit was chosen and anything known to be wrong with it.")
    first_year: int
    last_year: int
    latest_urban_centre_ghg_t_co2e: float = Field(
        description="Total GHG (t CO2e/yr, GWP100 AR5) in last_year, all EDGAR sectors. " + URBAN_CENTRE_CAVEAT)


class Page[T](_Model):
    items: list[T]
    total: int = Field(description="Matching items across all pages.")
    limit: int
    offset: int


class CitiesPage(Page[CitySummary]):
    """A page of cities; each item carries its own labels, flags and versions."""


# --- Emissions ---


class EmissionItem(_Model):
    year: int
    edgar_sector: EdgarSector
    gpc_sector_code: str = Field(description="GPC-aligned sector code (provisional, ADR 0002).")
    gpc_sector: str
    mapping_quality: Literal["direct", "approximate", "mixed"] = Field(
        description="How well the EDGAR sector maps to the GPC sector.")
    sector_mapping_review_status: ReviewStatus
    urban_centre_emissions: float = UrbanCentreEmissions


class EmissionsPage(_Model):
    city: CityContext
    pollutant: Pollutant
    unit: str = Field(examples=["t CO2e/yr"])
    is_ghg_total: bool = Field(description="True for the GHG total, which already contains CO2.")
    items: list[EmissionItem]
    total: int
    limit: int
    offset: int


class TrendItem(_Model):
    year: int
    prev_year: int | None = Field(description="Previous year with data (years are not annual). Null for the first.")
    urban_centre_emissions: float = Field(description="All EDGAR sectors summed. " + URBAN_CENTRE_CAVEAT)
    change_since_prev_pct: float | None
    annualised_change_pct: float | None = Field(description="Compound annual rate since prev_year, in percent.")
    sector_count: int


class TrendResponse(_Model):
    city: CityContext
    pollutant: Pollutant
    unit: str
    items: list[TrendItem]


class RevisionItem(_Model):
    pollutant: Pollutant
    unit: str
    edgar_sector: EdgarSector
    year: int
    revision_type: RevisionType = Field(
        description="`changed`, `added` (only in the newer version) or `removed` (only in the older).")
    from_edgar_version_id: int = Field(description="Older EDGAR version of the pair (usually not the current one).")
    to_edgar_version_id: int = Field(description="The next EDGAR version loaded after it.")
    from_urban_centre_emissions: float | None = Field(description=URBAN_CENTRE_CAVEAT + " Null if added.")
    to_urban_centre_emissions: float | None = Field(description=URBAN_CENTRE_CAVEAT + " Null if removed.")
    change: float | None
    change_pct: float | None


class RevisionsPage(_Model):
    city: CityContext
    items: list[RevisionItem]
    total: int
    limit: int
    offset: int


# --- Overlap and geometry ---


class Thresholds(_Model):
    min_urban_overlap: float
    suspect_crosswalk_overlap: float
    admin_area_tolerance: float


class OverlapResponse(_Model):
    city: CityContext
    admin_share_covered: float = Field(description="Share of the boundary's area covered by the urban centre.")
    iou: float = Field(description="Intersection over union of the two areas.")
    uc_area_km2: float
    admin_area_km2: float
    intersection_area_km2: float
    official_area_km2: float | None
    admin_area_vs_official: float | None = Field(description="admin_area_km2 / official_area_km2 - 1.")
    thresholds: Thresholds
    match_note: str


class MultiPolygon(_Model):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[list[float]]]]


class ShapeProperties(_Model):
    role: Literal["administrative_boundary", "urban_centre"]
    license: str = Field(description="Licence of the source file. Attribution is required.")
    source_url: str | None
    dataset_version_id: int
    gb_shape_id: str | None = None
    gb_shape_name: str | None = None
    gb_adm_level: str | None = None
    admin_area_km2: float | None = None
    official_area_km2: float | None = None


class Feature(_Model):
    type: Literal["Feature"]
    id: str
    geometry: MultiPolygon
    properties: ShapeProperties


class BoundaryFeatureCollection(_Model):
    """RFC 7946 FeatureCollection; `city` is a foreign member, which RFC 7946 allows."""

    type: Literal["FeatureCollection"]
    bbox: tuple[float, float, float, float] = Field(description="[west, south, east, north], both shapes.")
    features: list[Feature]
    city: CityContext


# --- Lineage ---


class DatasetVersion(_Model):
    dataset_version_id: int
    source_name: SourceName
    source_key: str
    origin: Literal["download", "sample", "synthetic"]
    is_current: bool = Field(description="True when reporting is built from this version.")
    source_url: str
    file_sha256: str
    license: str | None
    downloaded_at: datetime
    loaded_at: datetime
    row_count: int
    load_check_warnings: list[str]


class DatasetsPage(Page[DatasetVersion]):
    """A page of dataset versions."""
