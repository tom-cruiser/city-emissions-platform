"""Build the committed offline sample in data/sample/.

- geoBoundaries: real files, cut down to the crosswalk cities, from the latest *downloaded*
  versions in raw.dataset_versions (licences allow redistribution with attribution).
- EDGAR: a SYNTHETIC file with the real structure (see ingestion/synthetic.py). Real EDGAR
  rows are never written here: part of EDGAR is CC BY-NC-ND 4.0.

Each builder rewrites only its own source's entries in manifest.json, which records
where every sample file came from (upstream URL + SHA-256, or the generator).
"""

import json

import psycopg

from ingestion import config, synthetic
from ingestion.crosswalk import read_crosswalk
from ingestion.geoboundaries import read_features

LATEST_BOUNDARY_DOWNLOADS = """
    SELECT DISTINCT ON (source_key)
           source_key, source_url, file_path, file_sha256, license, downloaded_at
    FROM raw.dataset_versions
    WHERE origin = 'download' AND source_name = %s
    ORDER BY source_key, loaded_at DESC
"""

MANIFEST_DESCRIPTION = (
    "Offline sample used by tests, CI and first runs. geoBoundaries files are real "
    "extracts restricted to the cities in transform/seeds/city_crosswalk.csv. The EDGAR "
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
    manifest["files"] = sorted(kept + entries, key=lambda f: (f["source_name"], f["source_key"]))
    config.SAMPLE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def make_boundary_sample(conn: psycopg.Connection) -> list[dict]:
    shape_ids = {r["gb_shape_id"] for r in read_crosswalk()}
    entries, found = [], 0
    for key, url, file_path, sha, license_, downloaded_at in conn.execute(
        LATEST_BOUNDARY_DOWNLOADS, (config.GEOBOUNDARIES_SOURCE_NAME,)
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


def make_synthetic_edgar() -> dict:
    rel = f"edgar/{synthetic.FILENAME}"
    rows = synthetic.write_synthetic_edgar(config.SAMPLE_DIR / rel)
    entry = synthetic.manifest_entry(rel, rows)
    _update_manifest(config.EDGAR_SOURCE_NAME, [entry])
    return entry
