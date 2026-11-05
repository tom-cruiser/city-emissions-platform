import psycopg
import pytest

from ingestion.config import Settings


@pytest.fixture
def db_conn():
    """A connection whose work is always rolled back: tests leave no trace in the database.

    Skips (rather than fails) when Postgres is not running, so unit tests still run alone.
    """
    try:
        conn = psycopg.connect(Settings().pipeline_dsn, connect_timeout=3)
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")
    # The outer transaction is always rolled back. The pipeline's own
    # `conn.transaction()` blocks nest inside it as savepoints, so they cannot commit.
    try:
        with conn.transaction(force_rollback=True):
            yield conn
    finally:
        conn.close()
