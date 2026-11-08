"""Database access: one SQLAlchemy Core engine (a connection pool), read-only.

Three layers keep the API read-only and inside `reporting`:
1. The role: the reader role has SELECT on reporting only (db/init/lib/layers.sql).
2. The session: every connection sets default_transaction_read_only, so even a role with
   more rights could not write through the API.
3. A check on every new connection: if the role can use `raw` or `modelled`, or create
   anything in the database, the connection is refused (UnsafeDatabaseRoleError). The API
   fails closed when it is given the wrong credentials, instead of quietly working.
"""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import URL

from api.errors import UnsafeDatabaseRoleError
from api.settings import ApiSettings

_PRIVILEGE_CHECK = """
    select array_remove(array[
        case when has_schema_privilege('raw', 'USAGE') then 'USAGE on raw' end,
        case when has_schema_privilege('modelled', 'USAGE') then 'USAGE on modelled' end,
        case when has_schema_privilege('reporting', 'CREATE') then 'CREATE on reporting' end,
        case when has_database_privilege(current_database(), 'CREATE') then 'CREATE on the database' end
    ], null), current_user
"""


def _refuse_privileged_role(dbapi_connection, _record) -> None:
    with dbapi_connection.cursor() as cur:
        cur.execute(_PRIVILEGE_CHECK)
        too_much, user = cur.fetchone()
    dbapi_connection.rollback()  # hand the pool a connection with no open transaction
    if too_much:
        dbapi_connection.close()
        raise UnsafeDatabaseRoleError(f"role {user!r} has {', '.join(too_much)}")


def make_engine(settings: ApiSettings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
    engine = create_engine(
        url,
        pool_size=settings.pool_size,
        max_overflow=settings.pool_size,
        pool_pre_ping=True,  # a restarted database gives fresh connections, not errors
        connect_args={
            "connect_timeout": 3,
            "application_name": "city-emissions-api",
            "options": f"-c default_transaction_read_only=on -c statement_timeout={settings.statement_timeout_ms}",
        },
    )
    event.listen(engine, "connect", _refuse_privileged_role)
    return engine


@contextmanager
def snapshot(engine: Engine) -> Iterator[Connection]:
    """One read-only connection whose queries all see the same snapshot (REPEATABLE READ),
    so an endpoint that reads two tables never mixes two dbt builds' commits."""
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        yield conn


def fetch_all(conn: Connection, sql: str, params: Mapping[str, Any] | None = None) -> Sequence[Mapping[str, Any]]:
    return conn.execute(text(sql), dict(params or {})).mappings().all()


def fetch_one(conn: Connection, sql: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
    return conn.execute(text(sql), dict(params or {})).mappings().first()
