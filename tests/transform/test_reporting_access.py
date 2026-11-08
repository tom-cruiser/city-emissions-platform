"""The API's read-only role reads every reporting table, and nothing else.

Run after `dbt build --target test`: dbt drops and recreates every reporting table on
each build, and only ALTER DEFAULT PRIVILEGES (db/init/lib/layers.sql) gives the new
tables back to the reader. This connects AS the reader, the way the API will.
"""

import os

import psycopg
import pytest
from psycopg import sql

from tests.conftest import TEST_DB
from tests.transform.conftest import reporting_models


@pytest.fixture
def reader_conn():
    try:
        conn = psycopg.connect(TEST_DB.reader_dsn, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"test database required but not reachable: {exc}")
        pytest.skip(f"test database not reachable: {exc}")
    assert conn.info.dbname.endswith("_test")
    with conn:
        yield conn


def test_reader_reads_every_reporting_model(reader_conn, dbt_manifest):
    built = {r[0] for r in reader_conn.execute(
        "select table_name from information_schema.tables where table_schema = 'reporting'")}
    # information_schema only lists tables the current role has a privilege on, so a
    # table the reader cannot read looks "missing" here and fails below.
    if not built and os.environ.get("REQUIRE_TEST_DB") != "1":
        pytest.skip("reporting is empty in warehouse_test: run dbt build --target test first")
    problems = []
    for name in sorted(reporting_models(dbt_manifest)):
        try:
            n = reader_conn.execute(sql.SQL("select count(*) from reporting.{}").format(sql.Identifier(name))).fetchone()[0]
        except psycopg.Error as exc:
            problems.append(f"reporting.{name}: {exc.diag.message_primary}")
            continue
        if n == 0 and name != "city_emission_revisions":  # empty until a second EDGAR version exists
            problems.append(f"reporting.{name}: readable but empty")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("schema", ["raw", "modelled"])
def test_reader_cannot_read_raw_or_modelled(reader_conn, schema):
    table = {"raw": "dataset_versions", "modelled": "dim_city"}[schema]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        reader_conn.execute(sql.SQL("select 1 from {}.{} limit 1").format(sql.Identifier(schema), sql.Identifier(table)))
