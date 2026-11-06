"""Prove the test setup cannot reach the real warehouse."""

import psycopg
import pytest

from ingestion.config import Settings
from tests.conftest import TEST_DB


def test_fixture_is_connected_to_the_test_database(db_conn):
    assert db_conn.info.dbname == TEST_DB.test_postgres_db
    assert db_conn.info.user == TEST_DB.test_pipeline_user


def test_test_role_cannot_connect_to_the_real_warehouse(db_conn):
    real_db = TEST_DB.test_postgres_db.removesuffix("_test")
    with pytest.raises(psycopg.OperationalError, match="permission denied for database"):
        psycopg.connect(TEST_DB.dsn.replace(f"dbname={TEST_DB.test_postgres_db}", f"dbname={real_db}"),
                        connect_timeout=3)


def test_app_settings_are_redirected_to_the_test_database():
    settings = Settings()
    assert settings.postgres_db == TEST_DB.test_postgres_db
    assert settings.pipeline_user == TEST_DB.test_pipeline_user
