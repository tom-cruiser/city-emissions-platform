"""FastAPI application factory. Run with:

    uv run uvicorn --factory api.main:create_app

A factory, not a module-level `app`, so importing this module (tests, tooling) never
reads settings or needs database credentials."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from api import errors
from api.db import fetch_one, make_engine
from api.settings import ApiSettings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The pool connects lazily: the app starts even if the database is still down,
        # and /ready says so.
        app.state.engine = make_engine(settings)
        yield
        app.state.engine.dispose()

    app = FastAPI(title="City emissions API", version="1.0.0", lifespan=lifespan)
    errors.install(app)

    @app.get("/health", tags=["operations"], summary="Liveness: the process is up (no database call)")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["operations"], summary="Readiness: the database answers and reporting is built")
    def ready(engine: Engine = Depends(get_engine)):
        row = fetch_one(engine, "select count(*) filter (where is_current) as current_versions "
                                "from reporting.dataset_versions")
        if not row or not row["current_versions"]:
            return JSONResponse(status_code=503, content={
                "detail": "reporting has no current dataset versions: run the dbt build",
                "code": "reporting_not_built"})
        return {"status": "ready", "current_versions": row["current_versions"]}

    return app

