"""Build the committed offline sample in data/sample/.

- geoBoundaries: real files, cut down to the crosswalk cities, from the latest *downloaded*
  versions in raw.dataset_versions (licences allow redistribution with attribution).
- GHS-UCDB: a real GeoPackage cut down to the crosswalk's 25 urban centres (one layer,
  every attribute and vertex unchanged; CC BY 4.0 allows this with changes indicated).
- EDGAR: a SYNTHETIC file with the real structure (see ingestion/synthetic.py). Real EDGAR
  rows are never written here: part of EDGAR is CC BY-NC-ND 4.0.

Each builder rewrites only its own source's entries in manifest.json, which records
where every sample file came from (upstream URL + SHA-256, or the generator).
"""

import json
import sqlite3
from contextlib import closing

import psycopg

from ingestion import config, gpkg, synthetic
from ingestion.crosswalk import read_crosswalk
from ingestion.geoboundaries import read_features
from ingestion.ghs_ucdb import find_layer, gpkg_path_for

LATEST_DOWNLOADS = """
    SELECT DISTINCT ON (source_key)
           source_key, source_url, file_path, file_sha256, license, downloaded_at
    FROM raw.dataset_versions
    WHERE origin = 'download' AND source_name = %s
    ORDER BY source_key, loaded_at DESC
"""

MANIFEST_DESCRIPTION = (
    "Offline sample used by tests, CI and first runs. geoBoundaries and GHS-UCDB files are "
    "real extracts restricted to the cities in transform/seeds/city_crosswalk.csv. The EDGAR "
    "file is SYNTHETIC (invented values, real structure): real EDGAR rows are not "
    "redistributed. Rebuild with: python -m ingestion make-sample / make-synthetic"
)


def _update_manifest(source_name: str, entries: list[dict]) -> dict:
    """Replace this source's entries in manifest.json, keeping every other source's."""
    if config.SAMPLE_MANIFEST.exists():
        manifest = json.loads(config.SAMPLE_MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {"files": []}
    manifest["description"] = MANIFEST_DESCRIPTION
    kept = [f for f in manifest["files"] if f["source_name"] != source_name]
    # Within one (source_name, source_key), older files first: manifest order is load order,
    # and the last-loaded version of a file is the one dbt models (the synthetic EDGAR pair).
    manifest["files"] = sorted(kept + entries, key=lambda f: (
        f["source_name"], f["source_key"], f.get("generated_at") or f.get("upstream_downloaded_at") or ""))
    config.SAMPLE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def make_boundary_sample(conn: psycopg.Connection) -> list[dict]:
    shape_ids = {r["gb_shape_id"] for r in read_crosswalk()}
    entries, found = [], 0
    for key, url, file_path, sha, license_, downloaded_at in conn.execute(
        LATEST_DOWNLOADS, (config.GEOBOUNDARIES_SOURCE_NAME,)
    ):
        src = config.REPO_ROOT / file_path
        features = [f for f in read_features(src) if f["properties"].get("shapeID") in shape_ids]
        rel = f"geoboundaries/{src.name.split('_', 1)[1]}"  # drop the hash prefix
        dest = config.SAMPLE_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
            encoding="utf-8",
        )
        found += len(features)
        entries.append({
            "source_name": config.GEOBOUNDARIES_SOURCE_NAME, "source_key": key, "origin": "sample",
            "path": rel, "rows": len(features), "source_url": url, "license": license_,
            "upstream_sha256": sha, "upstream_downloaded_at": downloaded_at.isoformat(),
        })

    # A shapeID missing from the downloaded files means geoBoundaries re-issued IDs: fail loudly.
    if found != len(shape_ids):
        raise ValueError(f"found {found} of {len(shape_ids)} crosswalk boundary shapes")
    _update_manifest(config.GEOBOUNDARIES_SOURCE_NAME, entries)
    return entries


def make_synthetic_edgar() -> list[dict]:
    """Write the synthetic EDGAR fixture and its REVISED re-publication (two versions of
    v2024). Manifest order is load order: the revised file loads second, so it becomes the
    current version and the revisions models compare the two."""
    entries = []
    for revised, name in ((False, synthetic.FILENAME), (True, synthetic.REVISED_FILENAME)):
        rel = f"edgar/{name}"
        rows = synthetic.write_synthetic_edgar(config.SAMPLE_DIR / rel, revised=revised)
        entries.append(synthetic.manifest_entry(rel, rows, revised=revised))
    _update_manifest(config.EDGAR_SOURCE_NAME, entries)
    return entries


UCDB_SAMPLE_PATH = "ghs_ucdb/GHS_UCDB_GLOBE_R2024A_V1_2_crosswalk_cities.gpkg"
# GeoPackage metadata tables copied as-is (only the rows for the kept layer).
_GPKG_META = ("gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns")


def make_ucdb_sample(conn: psycopg.Connection) -> dict:
    """Write a GeoPackage holding only the crosswalk's urban centres, from the latest download.

    Kept: the one layer we load, its rows for the 25 crosswalk IDs (every attribute and
    vertex unchanged), and the GeoPackage metadata rows for that layer. Dropped: the other
    thematic layers, every other urban centre, and the R-tree spatial index.
    """
    downloads = conn.execute(LATEST_DOWNLOADS, (config.GHS_UCDB_SOURCE_NAME,)).fetchall()
    if not downloads:
        raise ValueError("no downloaded GHS-UCDB version in raw; run: load --mode download --source ghs_ucdb")
    key, url, file_path, sha, license_, downloaded_at = downloads[-1]
    src = gpkg_path_for(config.REPO_ROOT / file_path)
    layer = find_layer(src)
    ids = sorted(int(r["edgar_uc_id"]) for r in read_crosswalk())

    dest = config.SAMPLE_DIR / UCDB_SAMPLE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    table, id_col = layer.table, config.GHS_UCDB_ID_COLUMN
    with closing(sqlite3.connect(f"file:{dest}", uri=True)) as out:
        out.execute("ATTACH DATABASE ? AS src", (f"file:{src}?mode=ro",))
        app_id, user_version = (out.execute(f"PRAGMA src.{p}").fetchone()[0]
                                for p in ("application_id", "user_version"))
        out.execute(f"PRAGMA application_id = {int(app_id)}")
        out.execute(f"PRAGMA user_version = {int(user_version)}")
        for name in (*_GPKG_META, table):
            (ddl,) = out.execute("SELECT sql FROM src.sqlite_master WHERE type = 'table' AND name = ?",
                                 (name,)).fetchone()
            out.execute(ddl)
        out.execute("INSERT INTO gpkg_spatial_ref_sys SELECT * FROM src.gpkg_spatial_ref_sys")
        for meta in ("gpkg_contents", "gpkg_geometry_columns"):
            out.execute(f"INSERT INTO {meta} SELECT * FROM src.{meta} WHERE table_name = ?", (table,))
        out.execute(
            f'INSERT INTO "{table}" SELECT * FROM src."{table}" WHERE "{id_col}" IN ({",".join("?" * len(ids))})'
            " ORDER BY fid", ids)
        # gpkg_contents' bounds must describe the rows actually in this file.
        envs = [gpkg.parse_gpkg_blob(b).envelope for (b,) in out.execute(f'SELECT geom FROM "{table}"')]
        out.execute(
            "UPDATE gpkg_contents SET min_x = ?, max_x = ?, min_y = ?, max_y = ? WHERE table_name = ?",
            (min(e[0] for e in envs), max(e[1] for e in envs), min(e[2] for e in envs),
             max(e[3] for e in envs), table))
        out.commit()
        out.execute("DETACH DATABASE src")
        out.execute("VACUUM")
    rows = len(envs)
    if rows != len(ids):
        raise ValueError(f"found {rows} of {len(ids)} crosswalk urban centres in {src.name}")

    entry = {
        "source_name": config.GHS_UCDB_SOURCE_NAME, "source_key": key, "origin": "sample",
        "path": UCDB_SAMPLE_PATH, "rows": rows, "source_url": url,
        "license": license_ + ". Changes: subset to the 25 crosswalk urban centres and the "
                   f"{table} layer only; R-tree index dropped; attributes and geometries unchanged.",
        "upstream_sha256": sha, "upstream_downloaded_at": downloaded_at.isoformat(),
    }
    _update_manifest(config.GHS_UCDB_SOURCE_NAME, [entry])
    return entry
