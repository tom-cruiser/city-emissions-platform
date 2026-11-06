"""Load runs: 'download' (fetch the real files) and 'sample' (the small committed extract).

Each file is loaded in its own transaction: if Brazil's boundary file fails, the
files already loaded stay committed and a re-run skips them (same hash = no-op).
Careful: on an idle connection, `conn.transaction()` IS the outermost transaction and
commits when its block ends. To make a whole run undoable (as the tests do), call it
inside `with conn.transaction(force_rollback=True):` so each block becomes a savepoint.
"""

import json
from datetime import datetime

import httpx
import psycopg

from ingestion import config
from ingestion.crosswalk import boundary_files_needed
from ingestion.db import ensure_raw_tables
from ingestion.download import download, sha256_file
from ingestion.edgar import load_edgar
from ingestion.geoboundaries import load_geoboundaries, resolve_boundary_file
from ingestion.ghs_ucdb import LoadCheckError, load_ghs_ucdb
from ingestion.versioning import FileVersion, LoadResult

LOADERS = {
    config.EDGAR_SOURCE_NAME: load_edgar,
    config.GEOBOUNDARIES_SOURCE_NAME: load_geoboundaries,
    config.GHS_UCDB_SOURCE_NAME: load_ghs_ucdb,
}
SOURCES = {
    "edgar": config.EDGAR_SOURCE_NAME,
    "geoboundaries": config.GEOBOUNDARIES_SOURCE_NAME,
    "ghs_ucdb": config.GHS_UCDB_SOURCE_NAME,
}
# GHS-UCDB loads last: its ID check compares against the EDGAR version already in raw.
LOAD_ORDER = [config.EDGAR_SOURCE_NAME, config.GEOBOUNDARIES_SOURCE_NAME, config.GHS_UCDB_SOURCE_NAME]


def _load(conn: psycopg.Connection, fv: FileVersion) -> LoadResult:
    with conn.transaction():
        return LOADERS[fv.source_name](conn, fv)


def run_download(conn: psycopg.Connection, sources: list[str]) -> list[LoadResult]:
    with conn.transaction():
        ensure_raw_tables(conn)
    results = []
    client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, read=300))

    if config.EDGAR_SOURCE_NAME in sources:
        f = download(config.EDGAR_URL, config.RAW_DIR / "edgar", config.EDGAR_FILENAME, client=client)
        results.append(_load(conn, FileVersion(
            source_name=config.EDGAR_SOURCE_NAME, source_key=config.EDGAR_SOURCE_KEY,
            origin="download", source_url=config.EDGAR_URL, file_path=f.path, sha256=f.sha256,
            size_bytes=f.size_bytes, downloaded_at=f.downloaded_at, license=config.EDGAR_LICENSE,
        )))

    if config.GEOBOUNDARIES_SOURCE_NAME in sources:
        for iso3, level in boundary_files_needed():
            # Country files are independent: one failing must not block the other 20.
            try:
                bf = resolve_boundary_file(iso3, level, client)
                f = download(
                    bf.url, config.RAW_DIR / "geoboundaries",
                    f"geoBoundaries-{iso3}-{level}_simplified.geojson", client=client,
                )
                results.append(_load(conn, FileVersion(
                    source_name=config.GEOBOUNDARIES_SOURCE_NAME, source_key=f"{iso3}_{level}",
                    origin="download", source_url=bf.url, file_path=f.path, sha256=f.sha256,
                    size_bytes=f.size_bytes, downloaded_at=f.downloaded_at, license=bf.license,
                )))
            except (httpx.HTTPError, ValueError) as exc:
                results.append(LoadResult(
                    config.GEOBOUNDARIES_SOURCE_NAME, f"{iso3}_{level}", None, 0,
                    skipped=False, error=f"{type(exc).__name__}: {exc}",
                ))

    if config.GHS_UCDB_SOURCE_NAME in sources:
        f = download(config.GHS_UCDB_URL, config.RAW_DIR / "ghs_ucdb", config.GHS_UCDB_FILENAME, client=client)
        fv = FileVersion(
            source_name=config.GHS_UCDB_SOURCE_NAME, source_key=config.GHS_UCDB_SOURCE_KEY,
            origin="download", source_url=config.GHS_UCDB_URL, file_path=f.path, sha256=f.sha256,
            size_bytes=f.size_bytes, downloaded_at=f.downloaded_at, license=config.GHS_UCDB_LICENSE,
        )
        try:
            results.append(_load(conn, fv))
        except LoadCheckError as exc:
            results.append(LoadResult(fv.source_name, fv.source_key, None, 0, skipped=False, error=str(exc)))
    return results


def run_sample(conn: psycopg.Connection, sources: list[str]) -> list[LoadResult]:
    """Load the committed sample. Works offline: used by CI and the first `docker compose up`."""
    with conn.transaction():
        ensure_raw_tables(conn)
    manifest = json.loads(config.SAMPLE_MANIFEST.read_text(encoding="utf-8"))
    results = []
    for entry in sorted(manifest["files"], key=lambda e: LOAD_ORDER.index(e["source_name"])):
        if entry["source_name"] not in sources:
            continue
        path = config.SAMPLE_DIR / entry["path"]
        # 'sample' = real extract (has upstream hash + download time);
        # 'synthetic' = generated here (no upstream; its generation time stands in).
        obtained_at = entry.get("upstream_downloaded_at") or entry["generated_at"]
        results.append(_load(conn, FileVersion(
            source_name=entry["source_name"], source_key=entry["source_key"], origin=entry["origin"],
            source_url=entry["source_url"], file_path=path, sha256=sha256_file(path),
            size_bytes=path.stat().st_size, downloaded_at=datetime.fromisoformat(obtained_at),
            license=entry["license"], upstream_sha256=entry["upstream_sha256"],
        )))
    return results
