"""API tests run against warehouse_test as the TEST reader role, after:

    uv run python -m ingestion load --mode sample --target test
    scripts/dbt-build.sh test

If the database is unreachable or reporting is not built, DB-backed tests skip, or fail
under REQUIRE_TEST_DB=1 (CI)."""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings
from tests.conftest import TEST_DB


def _settings(**overrides) -> ApiSettings:
    values = {
        "db_host": TEST_DB.pghost, "db_port": TEST_DB.postgres_port, "db_name": TEST_DB.test_postgres_db,
        "db_user": TEST_DB.test_api_reader_user, "db_password": TEST_DB.test_api_reader_password,
    }
    values.update(overrides)
    return ApiSettings(**values)


def _skip_or_fail(reason: str) -> None:
    if os.environ.get("REQUIRE_TEST_DB") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def api_settings() -> ApiSettings:
    return _settings()


@pytest.fixture(scope="session")
def make_settings():
    """Settings for the test database with some values replaced (bad port, other role)."""
    return _settings


@pytest.fixture(scope="session")
def reporting_built(api_settings):
    """Skip unless warehouse_test is reachable and reporting has been built."""
    try:
        with psycopg.connect(TEST_DB.reader_dsn, connect_timeout=3) as conn:
            built = conn.execute("select to_regclass('reporting.cities') is not null").fetchone()[0]
    except psycopg.OperationalError as exc:
        _skip_or_fail(f"test database not reachable: {exc}")
    if not built:
        _skip_or_fail("reporting is not built in warehouse_test: run scripts/dbt-build.sh test")


@pytest.fixture(scope="session")
def client(api_settings, reporting_built):
    with TestClient(create_app(api_settings)) as c:
        yield c
