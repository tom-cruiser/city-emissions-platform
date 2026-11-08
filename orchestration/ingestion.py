"""The three sources as assets. Thin wrappers: the work is done by ingestion.pipeline,
the same functions the CLI (`python -m ingestion load`) calls.

Asset keys are the raw tables, named as the dbt source declares them
(transform/models/staging/_sources.yml), so dagster-dbt links them to the staging models
with no mapping code. Upstream of each: an external asset for the source file(s).
"""

from typing import Literal

import httpx
from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    Config,
    Failure,
    MaterializeResult,
    MetadataValue,
    RetryRequested,
    asset,
)

from ingestion import config as src
from ingestion.pipeline import run_download, run_sample
from ingestion.versioning import LoadResult
from orchestration.resources import Warehouse

GROUP = "ingestion"
EDGAR = AssetKey(["raw", "edgar_ucdb_emissions"])
GEOBOUNDARIES = AssetKey(["raw", "geoboundaries_features"])
GHS_UCDB = AssetKey(["raw", "ghs_ucdb_urban_centres"])
RAW_ASSETS = {src.EDGAR_SOURCE_NAME: EDGAR, src.GEOBOUNDARIES_SOURCE_NAME: GEOBOUNDARIES,
              src.GHS_UCDB_SOURCE_NAME: GHS_UCDB}

# Transient network errors: retried twice, a minute apart. Cheap, because files already
# loaded are skipped by SHA-256. Errors per file (a bad country file, a failed load check)
# are not retried: they fail the asset straight away.
DOWNLOAD_RETRIES = 2
RETRY_WAIT_SECONDS = 60


class LoadConfig(Config):
    mode: Literal["download", "sample"] = "download"
    """`download` fetches the real files. `sample` loads the committed offline sample, and
    is refused by any database not named *_test (ingestion.versioning.require_test_database)."""


source_files = [
    AssetSpec(["source", "edgar_ucdb"], group_name="sources", kinds={"xlsx"},
              description="EDGAR v2024 emissions per GHS urban centre (JRC). One workbook.",
              metadata={"url": MetadataValue.url(src.EDGAR_URL), "license": src.EDGAR_LICENSE}),
    AssetSpec(["source", "geoboundaries"], group_name="sources", kinds={"geojson"},
              description="geoBoundaries gbOpen, one simplified GeoJSON per country and level "
                          "needed by the crosswalk (24 files).",
              metadata={"api": src.GEOBOUNDARIES_API}),
    AssetSpec(["source", "ghs_ucdb"], group_name="sources", kinds={"gpkg"},
              description="GHS-UCDB R2024A urban-centre polygons (JRC GHSL). One zipped GeoPackage.",
              metadata={"url": MetadataValue.url(src.GHS_UCDB_URL), "license": src.GHS_UCDB_LICENSE}),
]

# Written by every loader. External (observed, not materialized here) so the staging
# models that read them still show which loaders feed them.
shared_raw_tables = [
    AssetSpec(["raw", "dataset_versions"], group_name=GROUP, deps=list(RAW_ASSETS.values()),
              description="One row per loaded file (SHA-256). Written by every ingestion asset."),
    AssetSpec(["raw", "load_checks"], group_name=GROUP, deps=list(RAW_ASSETS.values()),
              description="Load-time checks per dataset version (pass | warn)."),
]


def _results_table(results: list[LoadResult]) -> str:
    lines = ["| source_key | version | rows | outcome |", "|---|---|---|---|"]
    for r in results:
        outcome = (f"FAILED: {r.error}" if r.error else "already loaded" if r.skipped else "loaded")
        if r.warnings:
            outcome += f" (warnings: {', '.join(r.warnings)})"
        lines.append(f"| {r.source_key} | {r.dataset_version_id or ''} | {r.rows_loaded} | {outcome} |")
    return "\n".join(lines)


def load_source(context: AssetExecutionContext, warehouse: Warehouse, mode: str,
                source_name: str) -> MaterializeResult:
    run = run_sample if mode == "sample" else run_download
    try:
        with warehouse.connect() as conn:
            results = run(conn, [source_name])
    except httpx.HTTPError as exc:
        # Raised by a whole-source download (EDGAR, GHS-UCDB). Per-file errors come back as results.
        context.log.warning(f"download failed: {type(exc).__name__}: {exc}")
        raise RetryRequested(max_retries=DOWNLOAD_RETRIES, seconds_to_wait=RETRY_WAIT_SECONDS) from exc

    metadata = {
        "mode": mode,
        "files": len(results),
        "files_loaded": sum(1 for r in results if not r.error and not r.skipped),
        "files_already_loaded": sum(1 for r in results if r.skipped),
        "files_failed": sum(1 for r in results if r.error),
        "rows_loaded": sum(r.rows_loaded for r in results),
        "dataset_version_ids": [r.dataset_version_id for r in results if r.dataset_version_id],
        "results": MetadataValue.md(_results_table(results)),
    }
    failed = [r for r in results if r.error]
    if failed:
        # The other files ARE committed (one transaction per file); failing the asset makes
        # the run skip dbt, so reporting keeps the last good build until this is fixed.
        raise Failure(
            description=f"{len(failed)} of {len(results)} {source_name} file(s) failed: "
                        + "; ".join(f"{r.source_key}: {r.error}" for r in failed),
            metadata=metadata,
        )
    if not results:
        raise Failure(description=f"no {source_name} file was loaded or found", metadata=metadata)
    return MaterializeResult(metadata=metadata)


def _source_asset(key: AssetKey, source_name: str, file_spec: str, description: str, deps=()):
    @asset(key=key, group_name=GROUP, deps=[["source", file_spec], *deps],
           kinds={"python", "postgres"}, description=description)
    def _load(context: AssetExecutionContext, config: LoadConfig, warehouse: Warehouse) -> MaterializeResult:
        return load_source(context, warehouse, config.mode, source_name)

    return _load


raw_edgar = _source_asset(
    EDGAR, src.EDGAR_SOURCE_NAME, "edgar_ucdb",
    "EDGAR emissions per urban centre, one JSON record per sheet row. Raw, append-only, "
    "versioned by file SHA-256.")
raw_geoboundaries = _source_asset(
    GEOBOUNDARIES, src.GEOBOUNDARIES_SOURCE_NAME, "geoboundaries",
    "geoBoundaries features (WGS84), one dataset version per country file. A failing country "
    "file fails the asset; the other files stay loaded.")
raw_ghs_ucdb = _source_asset(
    GHS_UCDB, src.GHS_UCDB_SOURCE_NAME, "ghs_ucdb",
    "GHS-UCDB urban-centre polygons (ESRI:54009). Loads after EDGAR: its load check compares "
    "urban-centre IDs with the EDGAR version already in raw.",
    deps=[EDGAR])

ingestion_assets = [raw_edgar, raw_geoboundaries, raw_ghs_ucdb]
