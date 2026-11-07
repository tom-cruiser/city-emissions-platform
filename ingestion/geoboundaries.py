"""geoBoundaries (gbOpen) administrative boundaries: resolve, read, load into raw."""

import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ingestion.config import GEOBOUNDARIES_API
from ingestion.versioning import FileVersion, LoadResult, register_version


@dataclass(frozen=True)
class BoundaryFile:
    iso3: str
    level: str
    url: str  # commit-pinned GitHub URL: immutable for a given release
    license: str
    year: str


def resolve_boundary_file(iso3: str, level: str, client: httpx.Client) -> BoundaryFile:
    """Ask the geoBoundaries API which file is current for this country and level."""
    response = client.get(GEOBOUNDARIES_API.format(iso3=iso3, level=level))
    response.raise_for_status()
    meta = response.json()
    return BoundaryFile(
        iso3=iso3,
        level=level,
        url=meta["simplifiedGeometryGeoJSON"],
        license=meta["boundaryLicense"],
        year=str(meta["boundaryYearRepresented"]),
    )


def read_features(path: Path) -> list[dict]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return collection["features"]


def load_geoboundaries(conn: psycopg.Connection, fv: FileVersion) -> LoadResult:
    """Load every feature of one geoBoundaries file into raw. Does not commit."""
    features = read_features(fv.file_path)
    version_id, created = register_version(conn, fv, row_count=len(features))
    if not created:
        return LoadResult(fv.source_name, fv.source_key, version_id, 0, skipped=True)

    with conn.cursor() as cur, cur.copy(
        "COPY raw.geoboundaries_features"
        " (dataset_version_id, feature_index, properties, geometry) FROM STDIN"
    ) as copy:
        for index, feature in enumerate(features):
            copy.write_row((version_id, index, Jsonb(feature["properties"]), Jsonb(feature["geometry"])))

    return LoadResult(fv.source_name, fv.source_key, version_id, len(features), skipped=False)
