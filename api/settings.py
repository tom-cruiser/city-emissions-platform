"""API settings. Holds ONLY the read-only reader role's credentials: the API process is
never given the pipeline role's password, so it cannot write or read raw/modelled even
if a query were wrong."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]


class ApiSettings(BaseSettings):
    # Local runs read the repo's .env; in Docker the variables come from Compose and
    # there is no .env file (pydantic-settings skips a missing one).
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore", populate_by_name=True)

    db_host: str = Field("localhost", validation_alias="PGHOST")
    db_port: int = Field(5434, validation_alias="POSTGRES_PORT")
    db_name: str = Field("warehouse", validation_alias="POSTGRES_DB")
    db_user: str = Field("api_reader", validation_alias="API_READER_USER")
    db_password: SecretStr = Field(validation_alias="API_READER_PASSWORD")
    # Every statement is cancelled after this long; the API answers 503, not a hung request.
    statement_timeout_ms: int = Field(5000, validation_alias="API_STATEMENT_TIMEOUT_MS")
    pool_size: int = Field(5, validation_alias="API_DB_POOL_SIZE")
