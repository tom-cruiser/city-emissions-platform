"""Asset checks beyond the dbt tests (which dagster-dbt already turns into checks).

load_check_warnings, on each raw asset: the current version(s) of that source have no
`warn` row in raw.load_checks. WARN severity, never blocking: load-check warnings are
surfaced, not fatal, as everywhere else in the platform.

Freshness is not a check here but a FreshnessPolicy on the reporting tables
(orchestration/dbt.py, REPORTING_FRESHNESS): Dagster 1.13's replacement for freshness
checks, evaluated by the daemon with no sensor and no runs.
"""

from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetKey,
    MetadataValue,
    asset_check,
)

from orchestration.ingestion import RAW_ASSETS
from orchestration.resources import Warehouse

# Which origins staging reads per target: mirrors transform/macros/raw_origins.sql.
ORIGINS = {"warehouse": ["download"], "test": ["sample", "synthetic"]}

CURRENT_WARNINGS_SQL = """
with current_versions as (
    select distinct on (source_key) dataset_version_id, source_key
    from raw.dataset_versions
    where source_name = %(source_name)s and origin = any(%(origins)s)
    order by source_key, loaded_at desc, dataset_version_id desc
)
select v.source_key, v.dataset_version_id, c.check_name, c.detail::text
from current_versions as v
join raw.load_checks as c using (dataset_version_id)
where c.status = 'warn'
order by v.source_key, c.check_name
"""


def _load_check_warnings(source_name: str, asset_key: AssetKey):
    @asset_check(asset=asset_key, name="load_check_warnings", blocking=False,
                 description="The current version(s) of this source have no load-check warnings "
                             "(raw.load_checks). WARN only: warnings are surfaced, not fatal.")
    def _check(context: AssetCheckExecutionContext, warehouse: Warehouse) -> AssetCheckResult:
        with warehouse.connect() as conn:
            rows = conn.execute(CURRENT_WARNINGS_SQL, {
                "source_name": source_name, "origins": ORIGINS[warehouse.target]}).fetchall()
        table = "\n".join(["| source_key | version | check | detail |", "|---|---|---|---|",
                           *(f"| {k} | {v} | {c} | `{d[:200]}` |" for k, v, c, d in rows)])
        return AssetCheckResult(
            passed=not rows,
            severity=AssetCheckSeverity.WARN,
            description=f"{len(rows)} load-check warning(s) on the current version(s)" if rows else None,
            metadata={"warnings": len(rows), "details": MetadataValue.md(table)},
        )

    return _check


load_check_warnings = [_load_check_warnings(name, key) for name, key in RAW_ASSETS.items()]
