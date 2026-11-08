"""Lineage: the dataset versions every figure comes from."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import Engine

from api import queries as q
from api.db import fetch_all, fetch_one, snapshot
from api.errors import NotFoundError
from api.models import DatasetsPage, DatasetVersion, SourceName
from api.params import PaginationDep
from api.routers.cities import get_engine

router = APIRouter(prefix="/v1/datasets", tags=["lineage"])
EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("", response_model=DatasetsPage, summary="List dataset versions")
def list_datasets(
    engine: EngineDep, page: PaginationDep,
    source_name: Annotated[SourceName | None, Query()] = None,
    is_current: Annotated[bool | None, Query(description="Only current (true) or only older (false) versions.")] = None,
):
    params = {"source_name": source_name, "is_current": is_current, "limit": page.limit, "offset": page.offset}
    with snapshot(engine) as conn:
        rows = fetch_all(conn, q.DATASETS_PAGE, params)
        total = fetch_one(conn, q.DATASETS_COUNT, params)["n"]
    return {"items": [dict(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{dataset_version_id}", response_model=DatasetVersion, summary="One dataset version",
            responses={404: {"description": "Unknown dataset version"}})
def get_dataset(engine: EngineDep, dataset_version_id: Annotated[int, Path(ge=1)]):
    with snapshot(engine) as conn:
        row = fetch_one(conn, q.DATASET, {"id": dataset_version_id})
    if row is None:
        raise NotFoundError("dataset version", dataset_version_id, "dataset_version_not_found")
    return dict(row)
