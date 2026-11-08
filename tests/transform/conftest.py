"""Fixtures for tests of the dbt project in transform/."""

import os

import pytest
from dotenv import dotenv_values

from ingestion.config import REPO_ROOT

PROJECT_DIR = REPO_ROOT / "transform"


@pytest.fixture(scope="session")
def dbt_manifest(tmp_path_factory, _point_app_settings_at_test_db):
    """The dbt project parsed in-process (no database needed), for the test target.

    Parsed fresh into a temporary target path, so the result never depends on whatever
    an earlier `dbt build` left in transform/target. profiles.yml reads its connection
    settings from the environment; .env supplies any that are not set already.
    """
    from dbt.cli.main import dbtRunner

    for key, value in dotenv_values(REPO_ROOT / ".env").items():
        if value is not None:
            os.environ.setdefault(key, value)
    out = tmp_path_factory.mktemp("dbt")
    result = dbtRunner().invoke([
        "parse", "--project-dir", str(PROJECT_DIR), "--profiles-dir", str(PROJECT_DIR),
        "--target", "test", "--target-path", str(out / "target"), "--log-path", str(out / "logs"),
        "--quiet",
    ])
    assert result.success, f"dbt parse failed: {result.exception}"
    return result.result


def reporting_models(manifest) -> dict:
    """{model name: node} for every model built into the reporting schema."""
    return {
        node.name: node
        for node in manifest.nodes.values()
        if node.resource_type == "model" and node.config.schema == "reporting"
    }
