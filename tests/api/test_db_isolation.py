"""The API reaches the database only as the read-only reader role: it can read
`reporting` and nothing else, cannot write, and refuses to run with a stronger role.

These use the API's own engine (api.db.make_engine), not a separate connection, so they
test what the API actually does."""

import re
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.db import make_engine
from api.errors import UnsafeDatabaseRoleError
from api.main import create_app
from api.settings import REPO_ROOT
from tests.conftest import TEST_DB


@pytest.fixture
def engine(api_settings, reporting_built):
    e = make_engine(api_settings)
    yield e
    e.dispose()


def test_connects_as_the_reader_role(engine):
    with engine.connect() as c:
        assert c.execute(text("select current_user")).scalar() == TEST_DB.test_api_reader_user
        assert c.execute(text("show transaction_read_only")).scalar() == "on"


@pytest.mark.parametrize("relation", ["raw.dataset_versions", "raw.edgar_ucdb_emissions",
                                      "modelled.dim_city", "modelled.fct_city_emissions"])
def test_cannot_read_raw_or_modelled(engine, relation):
    with engine.connect() as c, pytest.raises(DBAPIError) as exc:
        c.execute(text(f"select 1 from {relation} limit 1"))
    assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)


def test_can_read_reporting(engine):
    with engine.connect() as c:
        assert c.execute(text("select count(*) from reporting.cities")).scalar() == 25


def test_cannot_write_reporting(engine):
    with engine.connect() as c, pytest.raises(DBAPIError) as exc:
        c.execute(text("delete from reporting.cities"))
    assert isinstance(exc.value.orig, (psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege))


def test_refuses_a_role_that_can_read_more(make_settings, reporting_built):
    """Given the pipeline role's credentials by mistake, the API fails closed."""
    settings = make_settings(db_user=TEST_DB.test_pipeline_user, db_password=TEST_DB.test_pipeline_password)
    e = make_engine(settings)
    try:
        with pytest.raises(UnsafeDatabaseRoleError, match="USAGE on raw"):
            e.connect()
    finally:
        e.dispose()
    with TestClient(create_app(settings)) as c:
        r = c.get("/ready")
    assert r.status_code == 500 and r.json()["code"] == "unsafe_database_role"


def test_api_sql_names_only_the_reporting_schema():
    """No query in the API's source mentions raw or modelled (the role would refuse it
    anyway; this catches the mistake before it reaches a database)."""
    offenders = [
        f"{p.relative_to(REPO_ROOT)}: {m.group(0)}"
        for p in (REPO_ROOT / "api").rglob("*.py")
        for m in re.finditer(r"\b(raw|modelled)\.[a-z_]+", p.read_text())
    ]
    assert not offenders, offenders
