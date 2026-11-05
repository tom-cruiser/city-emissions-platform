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

    @property
    def pipeline_dsn(self) -> str:
        return (
            f"host={self.pghost} port={self.postgres_port} dbname={self.postgres_db} "
            f"user={self.pipeline_user} password={self.pipeline_password}"
        )
