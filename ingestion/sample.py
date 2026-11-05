"""Build data/sample/ from the latest *downloaded* versions recorded in raw.dataset_versions.

The sample keeps each source's file format and layout, so the same loader code reads
both the sample and the real files. It keeps only the rows for cities in the crosswalk.
manifest.json records which upstream file (URL + SHA-256) each sample was cut from.
"""

import json
from pathlib import Path

import psycopg
from openpyxl import Workbook, load_workbook

from ingestion import config
from ingestion.crosswalk import read_crosswalk
from ingestion.geoboundaries import read_features

LATEST_DOWNLOADS = """
    SELECT DISTINCT ON (source_name, source_key)
           source_name, source_key, source_url, file_path, file_sha256, license, downloaded_at
    FROM raw.dataset_versions
    WHERE origin = 'download'
    ORDER BY source_name, source_key, loaded_at DESC
"""


def _write_edgar_sample(src: Path, dest: Path, uc_ids: set[int]) -> int:
    source = load_workbook(src, read_only=True, data_only=True)
    out = Workbook()
    out.remove(out.active)
    kept = 0
    for name in source.sheetnames:  # same sheets, same order
        target = out.create_sheet(name)
        rows = source[name].iter_rows(values_only=True)
        if name != config.EDGAR_DATA_SHEET:
            for row in rows:
                target.append(row)
            continue
        header = next(rows)
        target.append(header)
        id_col = header.index("ID_UC_G0")
        for row in rows:
            if row[id_col] in uc_ids:
                target.append(row)
                kept += 1
    source.close()
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest)
    return kept


def _write_geoboundaries_sample(src: Path, dest: Path, shape_ids: set[str]) -> int:
    features = [f for f in read_features(src) if f["properties"].get("shapeID") in shape_ids]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(features)


def make_sample(conn: psycopg.Connection) -> dict:
    crosswalk = read_crosswalk()
    uc_ids = {int(r["edgar_uc_id"]) for r in crosswalk}
    shape_ids = {r["gb_shape_id"] for r in crosswalk}

    files, found_shapes = [], 0
    for name, key, url, file_path, sha, license_, downloaded_at in conn.execute(LATEST_DOWNLOADS):
        src = config.REPO_ROOT / file_path
        if name == config.EDGAR_SOURCE_NAME:
            rel = f"edgar/{config.EDGAR_FILENAME}"
            kept = _write_edgar_sample(src, config.SAMPLE_DIR / rel, uc_ids)
            if kept != len(uc_ids):
                raise ValueError(f"EDGAR sample has {kept} rows, crosswalk has {len(uc_ids)} cities")
        else:
            rel = f"geoboundaries/{src.name.split('_', 1)[1]}"  # drop the hash prefix
            kept = _write_geoboundaries_sample(src, config.SAMPLE_DIR / rel, shape_ids)
            found_shapes += kept
        files.append({
            "source_name": name, "source_key": key, "path": rel, "rows": kept,
            "source_url": url, "license": license_, "upstream_sha256": sha,
            "upstream_downloaded_at": downloaded_at.isoformat(),
        })

    # A shapeID missing from the downloaded files means geoBoundaries re-issued IDs: fail loudly.
    if found_shapes != len(shape_ids):
        raise ValueError(f"found {found_shapes} of {len(shape_ids)} crosswalk boundary shapes")

    manifest = {
        "description": "Extract of real upstream files, restricted to the cities in "
                       "transform/seeds/city_crosswalk.csv. Regenerate with: "
                       "python -m ingestion make-sample",
        "files": files,
    }
    config.SAMPLE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest
