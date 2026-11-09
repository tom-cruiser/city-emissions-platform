"""The Dagster code location: `dagster dev -m orchestration.definitions`."""

from dagster import AssetSelection, DefaultScheduleStatus, Definitions, ScheduleDefinition, define_asset_job

from orchestration.checks import load_check_warnings
from orchestration.dbt import TARGET, dbt_models, dbt_resource
from orchestration.ingestion import ingestion_assets, shared_raw_tables, source_files
from orchestration.resources import Warehouse

# Every asset: the three loads, then one `dbt build`. A failed load skips dbt in that run.
weekly_refresh = define_asset_job(
    "weekly_refresh",
    selection=AssetSelection.all(),
    description="Download and load the three sources, then dbt build (models, snapshots, tests).",
)

# OFF by default: cloning the repo and starting Dagster never downloads anything unasked.
# Turn it on in the UI (Automation) or with `dagster schedule start`; production would.
# Weekly is to notice failures (a moved URL, a broken file) early, not because the sources
# change weekly: EDGAR is released about once a year, and unchanged files are skipped.
weekly_refresh_schedule = ScheduleDefinition(
    name="weekly_refresh_schedule",
    job=weekly_refresh,
    cron_schedule="0 3 * * 1",  # Mondays 03:00
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.STOPPED,
)

defs = Definitions(
    assets=[*source_files, *ingestion_assets, *shared_raw_tables, dbt_models],
    asset_checks=load_check_warnings,
    jobs=[weekly_refresh],
    schedules=[weekly_refresh_schedule],
    resources={"warehouse": Warehouse(target=TARGET), "dbt": dbt_resource},
)
