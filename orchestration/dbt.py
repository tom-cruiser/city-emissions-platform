"""Every dbt node (seeds, models, snapshots) as assets; dbt tests as asset checks.

One `dbt build` per run, against PIPELINE_TARGET. The raw tables are dbt sources whose
default asset keys (["raw", <table>]) are the ingestion assets' keys, so lineage runs
from the source file to the reporting tables.

The manifest is parsed per target into transform/target-dagster-<target>/ (the
test-only tests exist only in the `test` manifest). `dagster dev` re-parses on load; the
Docker image parses at build; otherwise it is parsed once if missing.
"""

import os
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from dagster import AssetExecutionContext, AssetSpec, FreshnessPolicy
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from ingestion.config import REPO_ROOT
from orchestration.resources import git_commit, pipeline_target

TARGET = pipeline_target()

dbt_project = DbtProject(
    project_dir=REPO_ROOT / "transform",
    profiles_dir=REPO_ROOT / "transform",
    target=TARGET,
    target_path=f"target-dagster-{TARGET}",
)
dbt_project.prepare_if_dev()
if not dbt_project.manifest_path.exists():
    dbt_project.preparer.prepare(dbt_project)


# Every reporting table must have been rebuilt by Dagster within 8 days: the weekly schedule
# plus a day of slack. It turns FAILED when the schedule is off or every run for a week has
# failed (a failed source skips dbt). Builds outside Dagster (scripts/dbt-build.sh) are not
# seen. Shown in the UI as the asset's freshness; evaluated by the daemon.
REPORTING_FRESHNESS = FreshnessPolicy.time_window(fail_window=timedelta(days=8))


class Translator(DagsterDbtTranslator):
    def get_asset_spec(self, manifest, unique_id, project) -> AssetSpec:
        spec = super().get_asset_spec(manifest, unique_id, project)
        if spec.group_name == "reporting":
            spec = spec.replace_attributes(freshness_policy=REPORTING_FRESHNESS)
        return spec

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        # Folder under models/ (staging, modelled, reporting), or seeds / snapshots.
        resource_type = dbt_resource_props["resource_type"]
        if resource_type == "model":
            return dbt_resource_props["fqn"][1]
        return {"seed": "seeds", "snapshot": "snapshots"}.get(resource_type)


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project, dagster_dbt_translator=Translator())
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    # The same rule as scripts/dbt-build.sh. dagster-dbt passes os.environ to the dbt
    # subprocess; this runs in the run's own worker process.
    os.environ["GIT_COMMIT"] = git_commit()
    context.log.info(f"dbt build --target {TARGET}  (GIT_COMMIT={os.environ['GIT_COMMIT']})")
    yield from dbt.cli(["build"], context=context).stream()


dbt_resource = DbtCliResource(project_dir=dbt_project, target=TARGET)
