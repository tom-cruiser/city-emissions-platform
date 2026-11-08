"""Test database wiring. Tests run against `warehouse_test`, never the real warehouse.

Three layers of protection:
1. Credentials: tests connect as the TEST_* roles, which have no CONNECT privilege on
   the real warehouse (db/init/02-test-db.sh). Pointing them at it fails in Postgres.
2. Guard: the session aborts if the configured test database name doesn't end in "_test".
3. Override: PIPELINE_* / POSTGRES_DB are replaced with the test values for the whole
   session, so any code that builds its own connection from Settings() also lands
   on the test database.

If the database is unreachable, DB tests are skipped so unit tests still run alone.
Set REQUIRE_TEST_DB=1 (CI does) to make that a failure instead.
"""

import os

import psycopg
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from ingestion.config import REPO_ROOT


class TestDbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    pghost: str = "localhost"
    postgres_port: int = 5434
    test_postgres_db: str = "warehouse_test"
    test_pipeline_user: str = "test_pipeline"
    test_pipeline_password: str = ""
    test_api_reader_user: str = "test_api_reader"
    test_api_reader_password: str = ""

    @property
    def dsn(self) -> str:
        return (
            f"host={self.pghost} port={self.postgres_port} dbname={self.test_postgres_db} "
            f"user={self.test_pipeline_user} password={self.test_pipeline_password}"
        )

    @property
    def reader_dsn(self) -> str:
        """The API's read-only test role: SELECT on reporting only."""
        return (
            f"host={self.pghost} port={self.postgres_port} dbname={self.test_postgres_db} "
            f"user={self.test_api_reader_user} password={self.test_api_reader_password}"
        )


TEST_DB = TestDbSettings()
if not TEST_DB.test_postgres_db.endswith("_test"):
    raise pytest.UsageError(
        f"refusing to run: TEST_POSTGRES_DB={TEST_DB.test_postgres_db!r} does not end in '_test'"
    )


@pytest.fixture(autouse=True, scope="session")
def _point_app_settings_at_test_db():
    overrides = {
        "POSTGRES_DB": TEST_DB.test_postgres_db,
        "PIPELINE_USER": TEST_DB.test_pipeline_user,
        "PIPELINE_PASSWORD": TEST_DB.test_pipeline_password,
    }
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)  # env vars take precedence over .env in pydantic-settings
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def db_conn():
    """A test-database connection whose work is always rolled back."""
    try:
        conn = psycopg.connect(TEST_DB.dsn, connect_timeout=3)
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"test database required but not reachable: {exc}")
        pytest.skip(f"test database not reachable: {exc}")

    assert conn.info.dbname.endswith("_test"), f"connected to {conn.info.dbname}, not a test database"

    # The outer transaction is always rolled back. The pipeline's own
    # `conn.transaction()` blocks nest inside it as savepoints, so they cannot commit.
    try:
        with conn.transaction(force_rollback=True):
            # warehouse_test may hold a committed sample load (dbt builds on it). Empty raw
            # for this test only: TRUNCATE is transactional, so the rollback restores it.
            if conn.execute("SELECT to_regclass('raw.dataset_versions')").fetchone()[0]:
                conn.execute("TRUNCATE raw.dataset_versions CASCADE")
            yield conn
    finally:
        conn.close()
