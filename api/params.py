"""Shared path and query parameters. Invalid values give 422 with FastAPI's standard body."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path, Query
from fastapi.exceptions import RequestValidationError

CityId = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64,
                             description="Platform city ID, e.g. `kigali-rwa`.", examples=["kigali-rwa"])]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: Annotated[int, Query(ge=1, le=100, description="Page size, 1-100.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip.")] = 0,
) -> Pagination:
    return Pagination(limit, offset)


@dataclass(frozen=True)
class YearRange:
    year_from: int | None
    year_to: int | None


def year_range(
    year_from: Annotated[int | None, Query(ge=1900, le=2100, description="First year, inclusive.")] = None,
    year_to: Annotated[int | None, Query(ge=1900, le=2100, description="Last year, inclusive.")] = None,
) -> YearRange:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise RequestValidationError([{
            "type": "value_error", "loc": ("query", "year_from"),
            "msg": "year_from must not be after year_to", "input": year_from,
        }])
    return YearRange(year_from, year_to)


PaginationDep = Annotated[Pagination, Depends(pagination)]
YearRangeDep = Annotated[YearRange, Depends(year_range)]
