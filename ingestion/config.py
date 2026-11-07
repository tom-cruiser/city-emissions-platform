"""Paths, source definitions and database settings for ingestion."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"  # full downloads (git-ignored)
SAMPLE_DIR = REPO_ROOT / "data" / "sample"  # small committed extracts
SAMPLE_MANIFEST = SAMPLE_DIR / "manifest.json"
CROSSWALK_CSV = REPO_ROOT / "transform" / "seeds" / "city_crosswalk.csv"

# --- EDGAR emissions in GHS urban centres -------------------------------------
EDGAR_SOURCE_NAME = "edgar_ucdb"
EDGAR_SOURCE_KEY = "v2024"
EDGAR_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EDGAR/datasets/"
    "global_emissions_in_urban_areas/v2024/EDGAR_emiss_on_UCDB_2024.xlsx"
)
EDGAR_FILENAME = "EDGAR_emiss_on_UCDB_2024.xlsx"
EDGAR_DATA_SHEET = "EDGAR_emiss_on_UCDB_2024"
EDGAR_VARIABLES_SHEET = "List of variables"
EDGAR_REQUIRED_COLUMNS = ("ID_UC_G0", "UC_name", "UC_country")
# Only what we could verify in the file itself; the general EDGAR licence text is truncated there.
EDGAR_LICENSE = (
    "(c) European Union 2024, JRC EDGAR. The IEA-EDGAR CO2 component (fossil fuel combustion) "
    "is licensed CC BY-NC-ND 4.0. See https://edgar.jrc.ec.europa.eu/dataset_ucdb"
)

# --- GHS Urban Centre Database (urban-centre polygons EDGAR is computed on) -----
GHS_UCDB_SOURCE_NAME = "ghs_ucdb"
GHS_UCDB_SOURCE_KEY = "R2024A_V1_2"
GHS_UCDB_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_UCDB_GLOBE_R2024A/"
    "GHS_UCDB_GLOBE_R2024A/V1-2/GHS_UCDB_GLOBE_R2024A_V1_2.zip"
)
GHS_UCDB_FILENAME = "GHS_UCDB_GLOBE_R2024A_V1_2.zip"
GHS_UCDB_GPKG_MEMBER = "GHS_UCDB_GLOBE_R2024A.gpkg"  # the zip also holds PDFs and an xlsx
# Every thematic layer repeats the same polygons; this one has ID, names, area, population.
GHS_UCDB_LAYER = "GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A"
GHS_UCDB_ID_COLUMN = "ID_UC_G0"  # the same ID EDGAR uses
GHS_UCDB_AREA_COLUMN = "GC_UCA_KM2_2025"  # source-declared area, km²
# World Mollweide (equal area). Downstream overlap ratios assume it, so the load fails otherwise.
GHS_UCDB_EXPECTED_SRS = ("ESRI", 54009)
GHS_UCDB_LICENSE = (
    "CC BY 4.0, (c) European Union 2024, JRC GHSL. Mari Rivero, I. et al. (2024): GHS-UCDB R2024A, "
    "doi:10.2905/1a338be6-7eaf-480c-9664-3a8ade88cbcd"
)

# --- geoBoundaries administrative boundaries ----------------------------------
GEOBOUNDARIES_SOURCE_NAME = "geoboundaries"
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{level}/"


class Settings(BaseSettings):
    """Database connection settings, read from the environment or the repo's .env file."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    pghost: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "warehouse"
    pipeline_user: str = "pipeline"
    pipeline_password: str = ""
    test_postgres_db: str = "warehouse_test"
    test_pipeline_user: str = "test_pipeline"
    test_pipeline_password: str = ""

    @property
    def pipeline_dsn(self) -> str:
        return self.dsn("warehouse")

    def dsn(self, target: str) -> str:
        """Connection string for a target: 'warehouse' (the real one) or 'test' (warehouse_test)."""
        if target == "test":
            db, user, password = self.test_postgres_db, self.test_pipeline_user, self.test_pipeline_password
        elif target == "warehouse":
            db, user, password = self.postgres_db, self.pipeline_user, self.pipeline_password
        else:
            raise ValueError(f"unknown target {target!r}")
        return f"host={self.pghost} port={self.postgres_port} dbname={db} user={user} password={password}"
