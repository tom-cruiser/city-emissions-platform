"""Sample and synthetic data must never be loaded into a database not named *_test."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ingestion import __main__ as cli
from ingestion.pipeline import SOURCES, run_sample
from ingestion.versioning import FileVersion, NotATestDatabaseError, register_version


class FakeConn:
    """Looks connected to `dbname`; any SQL at all fails the test (nothing may be written)."""

    def __init__(self, dbname: str):
        self.info = SimpleNamespace(dbname=dbname)

    def execute(self, *args, **kwargs):
        pytest.fail("SQL was executed before the guard refused the load")

    def transaction(self, *args, **kwargs):
        pytest.fail("a transaction was opened before the guard refused the load")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _file_version(origin: str) -> FileVersion:
    return FileVersion(
        source_name="edgar_ucdb", source_key="v2024", origin=origin, source_url="synthetic:x",
        file_path=Path("x.xlsx"), sha256="0" * 64, size_bytes=1, downloaded_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("dbname", ["warehouse", "warehouse_prod", "test_warehouse"])
def test_run_sample_refuses_a_non_test_database_before_writing(dbname):
    with pytest.raises(NotATestDatabaseError, match=dbname):
        run_sample(FakeConn(dbname), list(SOURCES.values()))


@pytest.mark.parametrize("origin", ["sample", "synthetic"])
def test_register_version_refuses_non_download_data_outside_test_db(origin):
    # The choke point every loader goes through, so custom code is stopped too.
    with pytest.raises(NotATestDatabaseError):
        register_version(FakeConn("warehouse"), _file_version(origin), row_count=1)


def test_cli_sample_load_into_warehouse_exits_with_an_error(monkeypatch, capsys):
    connected_to = []

    def fake_connect(dsn, **kwargs):
        connected_to.append(dsn)
        return FakeConn("warehouse")

    monkeypatch.setattr(cli.psycopg, "connect", fake_connect)
    monkeypatch.setattr(sys, "argv", ["python -m ingestion", "load", "--mode", "sample"])
    with pytest.raises(SystemExit, match="refusing to load the sample into database 'warehouse'"):
        cli.main()
    assert len(connected_to) == 1


def test_cli_requires_an_explicit_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["python -m ingestion", "load"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2  # argparse usage error


def test_sample_load_into_the_test_database_is_allowed(db_conn):
    assert db_conn.info.dbname.endswith("_test")
    results = run_sample(db_conn, list(SOURCES.values()))
    assert results and not any(r.error for r in results)
