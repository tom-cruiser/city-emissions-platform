"""Error responses. Every error body is {"detail": str, "code": str}, except 422, which
keeps FastAPI's standard validation body (a list of the parameters that failed)."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError

log = logging.getLogger("api")


class NotFoundError(Exception):
    def __init__(self, what: str, key: object, code: str):
        self.detail = f"{what} {key!r} not found"
        self.code = code


class UnsafeDatabaseRoleError(Exception):
    """The configured role can do more than read `reporting`. The API refuses to use it."""


def _error(status: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code})


def install(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _error(404, exc.detail, exc.code)

    @app.exception_handler(UnsafeDatabaseRoleError)
    async def unsafe_role(_: Request, exc: UnsafeDatabaseRoleError) -> JSONResponse:
        log.error("refusing database role: %s", exc)
        return _error(500, "the API is misconfigured: its database role is not read-only", "unsafe_database_role")

    @app.exception_handler(OperationalError)
    async def db_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        # Connection refused, timeouts and cancelled (too slow) statements.
        log.warning("database unavailable: %s", exc.orig)
        return _error(503, "the database is unavailable; try again later", "database_unavailable")

    @app.exception_handler(SQLAlchemyError)
    async def db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        log.exception("database error")  # details go to the log, never to the client
        return _error(500, "internal database error", "database_error")
