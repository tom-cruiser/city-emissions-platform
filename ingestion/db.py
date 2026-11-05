"""Database connection helpers."""

from pathlib import Path

import psycopg

from ingestion.config import Settings

RAW_DDL = Path(__file__).parent / "sql" / "raw_tables.sql"


def connect() -> psycopg.Connection:
    """Open a connection as the pipeline role.

    Use it as `with connect() as conn:`. psycopg commits when the block exits normally
    and rolls back if it raises, so a failed load leaves nothing half-written.
    """
    return psycopg.connect(Settings().pipeline_dsn)


def ensure_raw_tables(conn: psycopg.Connection) -> None:
    conn.execute(RAW_DDL.read_text())
