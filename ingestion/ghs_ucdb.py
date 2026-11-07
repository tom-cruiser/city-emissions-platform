"""GHS-UCDB R2024A urban-centre polygons: read the GeoPackage, load into raw, run load checks.

Stage 2 only *loads* polygons and checks the load. Overlap with administrative
boundaries is computed in dbt (Stage 3), where invalid polygons are also repaired.

Load checks (stored in raw.load_checks; a failing one raises and rolls the file back):

    row_count         features in the GeoPackage layer == rows written to raw
    gpkg_header       every blob's header SRS id matches the layer, and its envelope
                      matches the bounds PostGIS computes from the WKB
    srid              the layer's SRS resolves to ESRI:54009 in spatial_ref_sys, and every
                      stored geometry carries that SRID
    geometry_type     only (MULTI)POLYGON
    geometry_valid    ST_IsValid counts and reasons (warn, never fail); also confirms
                      ST_MakeValid repairs every one, which is what dbt staging will do
    area_vs_source    ST_Area in Mollweide vs the source's own km² column (equal-area sanity)
    id_match_edgar    IDs unique; every crosswalk city present; overlap with EDGAR's IDs
"""

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from ingestion import config, gpkg
from ingestion.crosswalk import read_crosswalk
from ingestion.versioning import FileVersion, LoadResult, register_version

SAMPLE_LIMIT = 20  # how many example IDs a check's detail lists


class LoadCheckError(ValueError):
    """A load check failed: the file's rows are rolled back."""


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # 'pass' | 'warn' | 'fail'
    detail: dict


def gpkg_path_for(file_path: Path) -> Path:
    """The GeoPackage to read: the file itself, or the one extracted next to a downloaded zip.

    The zip is what was downloaded and hashed (that is the dataset version); the .gpkg is a
    cache derived from it, named after the zip so a new zip never reuses an old extract.
    """
    if file_path.suffix.lower() == ".gpkg":
        return file_path
    target = file_path.with_suffix(".gpkg")
    with zipfile.ZipFile(file_path) as zf:
        info = zf.getinfo(config.GHS_UCDB_GPKG_MEMBER)
        if not (target.exists() and target.stat().st_size == info.file_size):
            part = target.with_name(f".{target.name}.part")
            with zf.open(info) as src, part.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            part.replace(target)
    return target


def find_layer(path: Path) -> gpkg.GpkgLayer:
    layers = {layer.table: layer for layer in gpkg.describe_layers(path)}
    if config.GHS_UCDB_LAYER not in layers:
        raise gpkg.GeoPackageError(
            f"{path.name}: layer {config.GHS_UCDB_LAYER!r} not found; layers are {sorted(layers)}"
        )
    return layers[config.GHS_UCDB_LAYER]


def postgis_srid(conn: psycopg.Connection, organization: str, org_id: int) -> int | None:
    row = conn.execute(
        "SELECT srid FROM spatial_ref_sys WHERE upper(auth_name) = %s AND auth_srid = %s",
        (organization.upper(), org_id),
    ).fetchone()
    return row[0] if row else None


def load_ghs_ucdb(conn: psycopg.Connection, fv: FileVersion) -> LoadResult:
    """Load the urban-centre layer into raw.ghs_ucdb_urban_centres, then check it. Does not commit."""
    path = gpkg_path_for(fv.file_path)
    layer = find_layer(path)

    # Resolve the SRID before writing anything: without it the geometries are meaningless.
    srid = postgis_srid(conn, layer.srs_organization, layer.srs_org_id)
    expected = config.GHS_UCDB_EXPECTED_SRS
    if srid is None or (layer.srs_organization, layer.srs_org_id) != expected:
        raise LoadCheckError(
            f"srid: layer SRS is {layer.srs_organization}:{layer.srs_org_id} "
            f"(PostGIS srid {srid}); expected {expected[0]}:{expected[1]} present in spatial_ref_sys"
        )

    version_id, created = register_version(conn, fv, row_count=layer.feature_count)
    if not created:
        return LoadResult(fv.source_name, fv.source_key, version_id, 0, skipped=True)

    conn.execute(
        """
        CREATE TEMP TABLE ghs_ucdb_stage (
            source_row_number integer, properties jsonb, wkb bytea,
            header_srs_id integer, env_minx float8, env_maxx float8, env_miny float8, env_maxy float8
        ) ON COMMIT DROP
        """
    )
    empty = []
    with conn.cursor() as cur, cur.copy("COPY ghs_ucdb_stage FROM STDIN") as copy:
        for n, (attrs, geom) in enumerate(gpkg.read_features(path, layer.table), start=1):
            if geom is None or geom.empty:
                empty.append(attrs.get(config.GHS_UCDB_ID_COLUMN))
                continue
            env = geom.envelope[:4] if geom.envelope else (None,) * 4
            copy.write_row((n, Jsonb(attrs), geom.wkb, geom.srs_id, *env))
    if empty:
        raise LoadCheckError(f"geometry: {len(empty)} features have no geometry, e.g. IDs {empty[:SAMPLE_LIMIT]}")

    conn.execute(
        """
        INSERT INTO raw.ghs_ucdb_urban_centres (dataset_version_id, source_row_number, properties, geom)
        SELECT %s, source_row_number, properties, ST_GeomFromWKB(wkb, %s)
        FROM ghs_ucdb_stage ORDER BY source_row_number
        """,
        (version_id, srid),
    )

    checks = run_checks(conn, version_id, layer, srid, fv.origin)
    conn.execute("DROP TABLE ghs_ucdb_stage")  # ON COMMIT DROP doesn't fire on a savepoint
    failed = [c for c in checks if c.status == "fail"]
    if failed:
        raise LoadCheckError("; ".join(f"{c.name}: {c.detail}" for c in failed))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO raw.load_checks (dataset_version_id, check_name, status, detail)"
            " VALUES (%s, %s, %s, %s)",
            [(version_id, c.name, c.status, Jsonb(c.detail)) for c in checks],
        )
    return LoadResult(
        fv.source_name, fv.source_key, version_id, layer.feature_count, skipped=False,
        warnings=tuple(f"{c.name}: {c.detail.get('summary', '')}" for c in checks if c.status == "warn"),
    )


def run_checks(conn: psycopg.Connection, version_id: int, layer: gpkg.GpkgLayer,
               srid: int, origin: str) -> list[Check]:
    return [
        _check_row_count(conn, version_id, layer),
        _check_gpkg_header(conn, layer),
        _check_srid(conn, version_id, layer, srid),
        _check_geometry_type(conn, version_id),
        _check_geometry_valid(conn, version_id),
        _check_area(conn, version_id),
        _check_id_match_edgar(conn, version_id, origin),
    ]


def _one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def _check_row_count(conn, version_id, layer) -> Check:
    (loaded,) = _one(conn, "SELECT count(*) FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s",
                     (version_id,))
    ok = loaded == layer.feature_count
    return Check("row_count", "pass" if ok else "fail", {
        "gpkg_features": layer.feature_count, "raw_rows": loaded,
        "summary": f"{loaded} of {layer.feature_count} features loaded",
    })


def _check_gpkg_header(conn, layer) -> Check:
    # 1 cm tolerance in Mollweide metres: header envelopes are written from the same doubles.
    wrong_srs, no_env, env_mismatch, sample = _one(conn, """
        WITH g AS (
            SELECT source_row_number, header_srs_id, env_minx, env_maxx, env_miny, env_maxy,
                   ST_GeomFromWKB(wkb) AS geom, properties->>%s AS id
            FROM ghs_ucdb_stage)
        SELECT count(*) FILTER (WHERE header_srs_id <> %s),
               count(*) FILTER (WHERE env_minx IS NULL),
               count(*) FILTER (WHERE env_minx IS NOT NULL AND greatest(
                   abs(env_minx - ST_XMin(geom)), abs(env_maxx - ST_XMax(geom)),
                   abs(env_miny - ST_YMin(geom)), abs(env_maxy - ST_YMax(geom))) > 0.01),
               (array_agg(id ORDER BY source_row_number) FILTER (WHERE env_minx IS NOT NULL AND greatest(
                   abs(env_minx - ST_XMin(geom)), abs(env_maxx - ST_XMax(geom)),
                   abs(env_miny - ST_YMin(geom)), abs(env_maxy - ST_YMax(geom))) > 0.01))[1:%s]
        FROM g
        """, (config.GHS_UCDB_ID_COLUMN, layer.srs_id, SAMPLE_LIMIT))
    ok = wrong_srs == 0 and env_mismatch == 0
    return Check("gpkg_header", "pass" if ok else "fail", {
        "header_srs_id_mismatch": wrong_srs, "without_envelope": no_env,
        "envelope_mismatch": env_mismatch, "envelope_mismatch_ids": sample or [],
        "summary": f"{wrong_srs} SRS id mismatches, {env_mismatch} envelope mismatches",
    })


def _check_srid(conn, version_id, layer, srid) -> Check:
    srids, srtext = _one(conn, """
        SELECT array_agg(DISTINCT ST_SRID(geom)),
               (SELECT left(srtext, 40) FROM spatial_ref_sys WHERE srid = %s)
        FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s
        """, (srid, version_id))
    ok = srids == [srid]
    return Check("srid", "pass" if ok else "fail", {
        "gpkg_srs": f"{layer.srs_organization}:{layer.srs_org_id}", "postgis_srid": srid,
        "stored_srids": srids, "srtext": srtext,
        "summary": f"all geometries SRID {srid} ({srtext})" if ok else f"SRIDs {srids}",
    })


def _check_geometry_type(conn, version_id) -> Check:
    types = dict(conn.execute("""
        SELECT GeometryType(geom), count(*) FROM raw.ghs_ucdb_urban_centres
        WHERE dataset_version_id = %s GROUP BY 1
        """, (version_id,)).fetchall())
    ok = set(types) <= {"POLYGON", "MULTIPOLYGON"}
    return Check("geometry_type", "pass" if ok else "fail", {"types": types, "summary": str(types)})


def _check_geometry_valid(conn, version_id) -> Check:
    crosswalk_ids = [int(r["edgar_uc_id"]) for r in read_crosswalk()]
    invalid, reasons, crosswalk_invalid, unrepaired = _one(conn, """
        WITH t AS (
            SELECT (properties->>%s)::bigint AS id, geom, NOT ST_IsValid(geom) AS invalid
            FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s)
        SELECT count(*) FILTER (WHERE invalid),
               (array_agg(id || ': ' || ST_IsValidReason(geom) ORDER BY id) FILTER (WHERE invalid))[1:%s],
               array_agg(id ORDER BY id) FILTER (WHERE invalid AND id = ANY(%s)),
               -- what dbt staging will do: repair, keep only the polygonal part
               count(*) FILTER (WHERE invalid AND NOT ST_IsValid(ST_CollectionExtract(ST_MakeValid(geom), 3)))
        FROM t
        """, (config.GHS_UCDB_ID_COLUMN, version_id, SAMPLE_LIMIT, crosswalk_ids))
    return Check("geometry_valid", "pass" if invalid == 0 else "warn", {
        "invalid": invalid, "examples": reasons or [], "crosswalk_cities_invalid": crosswalk_invalid or [],
        "still_invalid_after_make_valid": unrepaired,
        "summary": f"{invalid} invalid ({len(crosswalk_invalid or [])} crosswalk cities); "
                   f"{unrepaired} remain invalid after ST_MakeValid",
    })


def _check_area(conn, version_id) -> Check:
    """ST_Area in the native CRS should reproduce the source's own km² column if it is equal-area."""
    n, median, worst, worst_id = _one(conn, """
        WITH t AS (
            SELECT properties->>%s AS id,
                   abs(ST_Area(geom) / 1e6 / nullif((properties->>%s)::float8, 0) - 1) AS rel
            FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s)
        SELECT count(rel), percentile_cont(0.5) WITHIN GROUP (ORDER BY rel), max(rel),
               (array_agg(id ORDER BY rel DESC NULLS LAST))[1]
        FROM t
        """, (config.GHS_UCDB_ID_COLUMN, config.GHS_UCDB_AREA_COLUMN, version_id))
    ok = worst is not None and worst <= 0.05
    return Check("area_vs_source", "pass" if ok else "warn", {
        "compared": n, "median_rel_diff": median, "max_rel_diff": worst, "max_rel_diff_id": worst_id,
        "summary": f"ST_Area vs {config.GHS_UCDB_AREA_COLUMN}: median {median:.2%}, max {worst:.2%}"
                   if worst is not None else "no comparable rows",
    })


def _latest_edgar_version(conn, origin: str) -> int | None:
    """Compare a download with a download, and a sample with the offline (synthetic) EDGAR."""
    row = _one(conn, """
        SELECT max(dataset_version_id) FROM raw.dataset_versions
        WHERE source_name = %s AND (origin = 'download') = (%s = 'download')
        """, (config.EDGAR_SOURCE_NAME, origin))
    return row[0]


def _check_id_match_edgar(conn, version_id, origin) -> Check:
    crosswalk_ids = sorted(int(r["edgar_uc_id"]) for r in read_crosswalk())
    ucdb_ids = [r[0] for r in conn.execute(
        "SELECT (properties->>%s)::bigint FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s",
        (config.GHS_UCDB_ID_COLUMN, version_id))]
    ucdb = set(ucdb_ids)
    detail: dict = {
        "ucdb_ids": len(ucdb), "ucdb_null_ids": sum(i is None for i in ucdb_ids),
        "ucdb_duplicate_ids": len(ucdb_ids) - len(ucdb),
        "crosswalk_missing_in_ucdb": [i for i in crosswalk_ids if i not in ucdb],
    }
    fail = detail["ucdb_null_ids"] or detail["ucdb_duplicate_ids"] or detail["crosswalk_missing_in_ucdb"]

    edgar_version = _latest_edgar_version(conn, origin)
    detail["edgar_version_id"] = edgar_version
    if edgar_version is None:
        detail["summary"] = "no EDGAR version loaded to compare with"
        return Check("id_match_edgar", "fail" if fail else "warn", detail)

    edgar = {r[0] for r in conn.execute(
        "SELECT (record->>'ID_UC_G0')::numeric::bigint FROM raw.edgar_ucdb_emissions"
        " WHERE dataset_version_id = %s", (edgar_version,))}
    edgar_only, ucdb_only = sorted(edgar - ucdb), sorted(ucdb - edgar)
    detail |= {
        "edgar_ids": len(edgar), "matched": len(edgar & ucdb),
        "edgar_only": len(edgar_only), "edgar_only_examples": edgar_only[:SAMPLE_LIMIT],
        "ucdb_only": len(ucdb_only), "ucdb_only_examples": ucdb_only[:SAMPLE_LIMIT],
        "crosswalk_missing_in_edgar": [i for i in crosswalk_ids if i not in edgar],
        "summary": f"{len(edgar & ucdb)} IDs matched; {len(edgar_only)} EDGAR-only, "
                   f"{len(ucdb_only)} UCDB-only (EDGAR version {edgar_version})",
    }
    status = "fail" if fail else ("pass" if not edgar_only and not ucdb_only else "warn")
    return Check("id_match_edgar", status, detail)
