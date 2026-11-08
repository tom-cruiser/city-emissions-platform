"""The Dagster code location: `dagster dev -m orchestration.definitions`."""

from dagster import Definitions

from orchestration.dbt import TARGET, dbt_models, dbt_resource
from orchestration.ingestion import ingestion_assets, shared_raw_tables, source_files
from orchestration.resources import Warehouse

defs = Definitions(
    assets=[*source_files, *ingestion_assets, *shared_raw_tables, dbt_models],
    resources={"warehouse": Warehouse(target=TARGET), "dbt": dbt_resource},
)
