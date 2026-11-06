"""Minimal GeoPackage reader: stdlib sqlite3 plus the GPKG geometry-blob header.

No GDAL needed. A GeoPackage is a SQLite file; each geometry is stored as a
"GeoPackageBinary" blob (OGC 12-128r19, section 2.1.3):

    magic 'GP' | version (1 byte) | flags (1 byte) | srs_id (int32)
    | envelope (0, 4, 6, 6 or 8 doubles) | WKB geometry

Flags: bit 0 = byte order of srs_id and envelope (1 = little endian),
bits 1-3 = envelope contents indicator, bit 4 = empty geometry,
bit 5 = ExtendedGeoPackageBinary (non-standard geometry types; rejected here).

We return the WKB untouched. PostGIS turns it into a geometry with the SRID
resolved from gpkg_spatial_ref_sys, so no coordinate is ever rewritten in Python.
"""

import sqlite3
import struct
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

# Envelope contents indicator -> number of doubles: none, xy, xyz, xym, xyzm.
_ENVELOPE_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}


class GeoPackageError(ValueError):
    """The file or a geometry blob is not what the GeoPackage spec says it should be."""


@dataclass(frozen=True)
class GpkgGeometry:
    srs_id: int
    envelope: tuple[float, ...]  # (minx, maxx, miny, maxy[, ...]) as in the spec; () if absent
    empty: bool
    wkb: bytes


def parse_gpkg_blob(blob: bytes) -> GpkgGeometry:
    """Split a GeoPackageBinary blob into its header fields and the WKB payload."""
    if len(blob) < 8 or blob[:2] != b"GP":
        raise GeoPackageError("not a GeoPackage geometry blob (missing 'GP' magic)")
    version, flags = blob[2], blob[3]
    if version != 0:
        raise GeoPackageError(f"unsupported GeoPackageBinary version {version}")
    if flags & 0b0010_0000:
        raise GeoPackageError("ExtendedGeoPackageBinary geometries are not supported")
    indicator = (flags >> 1) & 0b111
    if indicator not in _ENVELOPE_DOUBLES:
        raise GeoPackageError(f"invalid envelope contents indicator {indicator}")

    order = "<" if flags & 1 else ">"
    (srs_id,) = struct.unpack_from(f"{order}i", blob, 4)
    n = _ENVELOPE_DOUBLES[indicator]
    end = 8 + 8 * n
    if len(blob) < end + 5:  # at least a WKB byte-order byte + type
        raise GeoPackageError("blob is shorter than its header says")
    envelope = struct.unpack_from(f"{order}{n}d", blob, 8) if n else ()
    return GpkgGeometry(srs_id, envelope, bool(flags & 0b1_0000), blob[end:])


@dataclass(frozen=True)
class GpkgLayer:
    table: str
    geometry_column: str
    srs_id: int
    srs_organization: str  # e.g. 'ESRI', 'EPSG'
    srs_org_id: int  # e.g. 54009
    feature_count: int


def describe_layers(path: Path) -> list[GpkgLayer]:
    """The feature tables declared in gpkg_geometry_columns, with their SRS."""
    with closing(_open(path)) as db:
        rows = db.execute(
            """
            SELECT g.table_name, g.column_name, g.srs_id, s.organization, s.organization_coordsys_id
            FROM gpkg_geometry_columns g
            JOIN gpkg_spatial_ref_sys s USING (srs_id)
            ORDER BY g.table_name
            """
        ).fetchall()
        return [
            GpkgLayer(t, c, srs, org.upper(), org_id,
                      db.execute(f'SELECT count(*) FROM "{_ident(t)}"').fetchone()[0])
            for t, c, srs, org, org_id in rows
        ]


def read_features(path: Path, table: str) -> Iterator[tuple[dict, GpkgGeometry | None]]:
    """Yield (attributes, geometry) per row in primary-key order. Attributes exclude the geometry."""
    layer = next((l for l in describe_layers(path) if l.table == table), None)
    if layer is None:
        raise GeoPackageError(f"{path.name}: no feature table {table!r}")
    with closing(_open(path)) as db:
        cur = db.execute(f'SELECT * FROM "{_ident(table)}" ORDER BY rowid')
        names = [d[0] for d in cur.description]
        for row in cur:
            attrs = dict(zip(names, row))
            blob = attrs.pop(layer.geometry_column)
            yield attrs, (parse_gpkg_blob(blob) if blob is not None else None)


def _open(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise GeoPackageError(f"{path} does not exist")
    # Read-only URI: a reader must never modify (or create) the source file.
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        (app_id,) = db.execute("PRAGMA application_id").fetchone()
    except sqlite3.DatabaseError as exc:
        db.close()
        raise GeoPackageError(f"{path.name} is not a SQLite/GeoPackage file: {exc}") from exc
    if app_id != 0x47504B47:  # 'GPKG'
        db.close()
        raise GeoPackageError(f"{path.name} is not a GeoPackage (application_id {app_id:#x})")
    return db


def _ident(name: str) -> str:
    """Table names come from the file itself; still refuse anything that could break quoting."""
    if '"' in name or "\x00" in name:
        raise GeoPackageError(f"refusing suspicious table name {name!r}")
    return name
