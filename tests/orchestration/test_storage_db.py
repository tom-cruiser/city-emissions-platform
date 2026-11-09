"""Dagster's storage database (db/init/03-dagster-db.sh) is isolated from the warehouses.

Connection-level checks only: nothing is written anywhere.
"""

import os

import psycopg
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from ingestion.config import REPO_ROOT
from tests.conftest import TEST_DB


class Creds(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    pghost: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "warehouse"
    dagster_pg_db: str = "dagster"
    dagster_pg_user: str = "dagster"
    dagster_pg_password: str = ""
    pipeline_user: str = "pipeline"
    pipeline_password: str = ""
    api_reader_user: str = "api_reader"
    api_reader_password: str = ""


# Read at import, i.e. before conftest's session fixture points POSTGRES_DB / PIPELINE_* at
# the test values: these are the real warehouse's names, used only for refused connections.
CREDS = Creds()


def connect(dbname: str, user: str, password: str) -> psycopg.Connection:
    return psycopg.connect(host=CREDS.pghost, port=CREDS.postgres_port, dbname=dbname,
                           user=user, password=password, connect_timeout=3)


@pytest.fixture(scope="module")
def dagster_db_ready():
    try:
        connect(CREDS.dagster_pg_db, CREDS.dagster_pg_user, CREDS.dagster_pg_password).close()
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"Dagster storage database unreachable: {exc}")
        pytest.skip(f"Dagster storage database unreachable: {exc}")


def assert_refused(dbname: str, user: str, password: str) -> None:
    with pytest.raises(psycopg.OperationalError, match="permission denied for database"):
        connect(dbname, user, password).close()


def test_dagster_role_owns_its_database(dagster_db_ready):
    with connect(CREDS.dagster_pg_db, CREDS.dagster_pg_user, CREDS.dagster_pg_password) as conn:
        owner, superuser = conn.execute(
            "SELECT pg_get_userbyid(d.datdba), r.rolsuper FROM pg_database d, pg_roles r "
            "WHERE d.datname = current_database() AND r.rolname = current_user").fetchone()
    assert owner == CREDS.dagster_pg_user
    assert superuser is False


@pytest.mark.parametrize("dbname", [CREDS.postgres_db, TEST_DB.test_postgres_db])
def test_dagster_role_cannot_reach_warehouses(dagster_db_ready, dbname):
    assert_refused(dbname, CREDS.dagster_pg_user, CREDS.dagster_pg_password)


def test_warehouse_roles_cannot_reach_dagster_db(dagster_db_ready):
    assert_refused(CREDS.dagster_pg_db, TEST_DB.test_pipeline_user, TEST_DB.test_pipeline_password)
    assert_refused(CREDS.dagster_pg_db, TEST_DB.test_api_reader_user, TEST_DB.test_api_reader_password)
    assert_refused(CREDS.dagster_pg_db, CREDS.pipeline_user, CREDS.pipeline_password)
    assert_refused(CREDS.dagster_pg_db, CREDS.api_reader_user, CREDS.api_reader_password)
