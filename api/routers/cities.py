"""City-scoped endpoints. Every response carries the city's context block (labels, flags,
review status, version ids); see api/docs.py for why."""

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, Engine

from api import queries as q
from api.db import fetch_all, fetch_one, snapshot
from api.errors import NotFoundError
from api.models import (
    BoundaryFeatureCollection,
    CitiesPage,
    CityContext,
    CitySummary,
    EdgarSector,
    EmissionsPage,
    Flag,
    OverlapResponse,
    Pollutant,
    ReviewStatus,
    RevisionsPage,
    RevisionType,
    TrendResponse,
)
from api.params import CityId, PaginationDep, YearRangeDep

router = APIRouter(prefix="/v1/cities")


def get_engine():  # replaced in main.create_app; declared here so routes can depend on it
    raise NotImplementedError


EngineDep = Annotated[Engine, Depends(get_engine)]


def _context(row: Mapping[str, Any]) -> dict[str, Any]:
    c = {k: row[k] for k in CityContext.model_fields if k != "versions"}
    c["versions"] = {"edgar": row["edgar_version_id"], "ghs_ucdb": row["ucdb_version_id"],
                     "geoboundaries": row["gb_version_id"]}
    return c


def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return _context(row) | {k: row[k] for k in CitySummary.model_fields if k not in CityContext.model_fields}


def _city(conn: Connection, city_id: str) -> Mapping[str, Any]:
    row = fetch_one(conn, q.CITY, {"city_id": city_id})
    if row is None:
        raise NotFoundError("city", city_id, "city_not_found")
    return row


class GeoJSONResponse(JSONResponse):
    media_type = "application/geo+json"


@router.get("", response_model=CitiesPage, tags=["cities"], summary="List cities")
def list_cities(
    engine: EngineDep,
    page: PaginationDep,
    country: Annotated[list[str] | None, Query(pattern=r"^[A-Z]{3}$", description="ISO 3166-1 alpha-3; repeatable.")] = None,
    review_status: Annotated[ReviewStatus | None, Query(description="Crosswalk review status.")] = None,
    flag: Annotated[list[Flag] | None, Query(description="Only cities with ALL these flags set; repeatable.")] = None,
):
    params = {"countries": country, "review_status": review_status,
              "flags": [f.value for f in flag] if flag else None,
              "limit": page.limit, "offset": page.offset}
    with snapshot(engine) as conn:
        rows = fetch_all(conn, q.CITIES_PAGE, params)
        total = fetch_one(conn, q.CITIES_COUNT, params)["n"]
    return {"items": [_summary(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{city_id}", response_model=CitySummary, tags=["cities"], summary="One city",
            responses={404: {"description": "Unknown city"}})
def get_city(engine: EngineDep, city_id: CityId):
    with snapshot(engine) as conn:
        return _summary(_city(conn, city_id))


@router.get("/{city_id}/emissions", response_model=EmissionsPage, tags=["emissions"],
            summary="Urban-centre emissions by EDGAR sector and year (one pollutant)",
            responses={404: {"description": "Unknown city"}})
def get_emissions(
    engine: EngineDep, city_id: CityId, page: PaginationDep, years: YearRangeDep,
    pollutant: Annotated[Pollutant, Query(description="Exactly one: pollutants are never added together.")] = Pollutant.GHG,
    sector: Annotated[list[EdgarSector] | None, Query(description="EDGAR sectors; repeatable. Default: all.")] = None,
):
    params = {"city_id": city_id, "pollutant": pollutant.value,
              "sectors": [s.value for s in sector] if sector else None,
              "year_from": years.year_from, "year_to": years.year_to,
              "limit": page.limit, "offset": page.offset}
    with snapshot(engine) as conn:
        city = _city(conn, city_id)
        rows = fetch_all(conn, q.EMISSIONS_PAGE, params)
        total = fetch_one(conn, q.EMISSIONS_COUNT, params)["n"]
        unit = fetch_one(conn, q.POLLUTANT_UNIT, {"pollutant": pollutant.value})
    return {"city": _context(city), "pollutant": pollutant, "unit": unit["unit"],
            "is_ghg_total": unit["is_ghg_total"], "items": [dict(r) for r in rows],
            "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{city_id}/trend", response_model=TrendResponse, tags=["emissions"],
            summary="Urban-centre emissions per year, all sectors (one pollutant)",
            responses={404: {"description": "Unknown city"}})
def get_trend(
    engine: EngineDep, city_id: CityId, years: YearRangeDep,
    pollutant: Annotated[Pollutant, Query(description="Exactly one pollutant.")] = Pollutant.GHG,
):
    params = {"city_id": city_id, "pollutant": pollutant.value,
              "year_from": years.year_from, "year_to": years.year_to}
    with snapshot(engine) as conn:
        city = _city(conn, city_id)
        rows = fetch_all(conn, q.TREND, params)
        unit = fetch_one(conn, q.POLLUTANT_UNIT, {"pollutant": pollutant.value})
    return {"city": _context(city), "pollutant": pollutant, "unit": unit["unit"],
            "items": [{k: v for k, v in r.items() if k != "unit"} for r in rows]}


@router.get("/{city_id}/revisions", response_model=RevisionsPage, tags=["emissions"],
            summary="Changes between consecutive EDGAR versions",
            responses={404: {"description": "Unknown city"}})
def get_revisions(
    engine: EngineDep, city_id: CityId, page: PaginationDep,
    revision_type: Annotated[RevisionType | None, Query()] = None,
    pollutant: Annotated[Pollutant | None, Query()] = None,
):
    params = {"city_id": city_id, "revision_type": revision_type,
              "pollutant": pollutant.value if pollutant else None,
              "limit": page.limit, "offset": page.offset}
    with snapshot(engine) as conn:
        city = _city(conn, city_id)
        rows = fetch_all(conn, q.REVISIONS_PAGE, params)
        total = fetch_one(conn, q.REVISIONS_COUNT, params)["n"]
    return {"city": _context(city), "items": [dict(r) for r in rows],
            "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{city_id}/overlap", response_model=OverlapResponse, tags=["geometry"],
            summary="Overlap of the urban centre with the administrative boundary",
            responses={404: {"description": "Unknown city"}})
def get_overlap(engine: EngineDep, city_id: CityId):
    with snapshot(engine) as conn:
        city = _city(conn, city_id)
        o = fetch_one(conn, q.OVERLAP, {"city_id": city_id})
    thresholds = {k: o[k] for k in ("min_urban_overlap", "suspect_crosswalk_overlap", "admin_area_tolerance")}
    rest = {k: v for k, v in o.items() if k not in thresholds}
    return {"city": _context(city), "thresholds": thresholds, **rest}


@router.get("/{city_id}/boundary", response_model=BoundaryFeatureCollection, response_class=GeoJSONResponse,
            tags=["geometry"], summary="Boundary and urban centre as GeoJSON",
            responses={200: {"content": {"application/geo+json": {}}}, 404: {"description": "Unknown city"}})
def get_boundary(engine: EngineDep, city_id: CityId):
    with snapshot(engine) as conn:
        city = _city(conn, city_id)
        b = fetch_one(conn, q.BOUNDARY, {"city_id": city_id})
    boundary = {
        "type": "Feature", "id": "administrative_boundary", "geometry": b["boundary_geojson"],
        "properties": {"role": "administrative_boundary", "license": b["boundary_license"],
                       "source_url": b["boundary_source_url"], "dataset_version_id": b["gb_version_id"],
                       "gb_shape_id": b["gb_shape_id"], "gb_shape_name": b["gb_shape_name"],
                       "gb_adm_level": b["gb_adm_level"], "admin_area_km2": b["admin_area_km2"],
                       "official_area_km2": b["official_area_km2"]},
    }
    urban_centre = {
        "type": "Feature", "id": "urban_centre", "geometry": b["urban_centre_geojson"],
        "properties": {"role": "urban_centre", "license": b["urban_centre_license"], "source_url": None,
                       "dataset_version_id": b["ucdb_version_id"]},
    }
    return {"type": "FeatureCollection", "bbox": b["bbox"], "features": [boundary, urban_centre],
            "city": _context(city)}
