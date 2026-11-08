"""Fixtures for the Dagster code location. Everything runs with PIPELINE_TARGET=test.

orchestration/ reads PIPELINE_TARGET at import, so it is imported inside the fixture,
after the target and the test database settings are in place.
"""

import importlib
import os

import pytest
from dotenv import dotenv_values

from ingestion.config import REPO_ROOT


@pytest.fixture(scope="session")
def defs(_point_app_settings_at_test_db):
    os.environ["PIPELINE_TARGET"] = "test"
    # profiles.yml reads its connection settings from the environment.
    for key, value in dotenv_values(REPO_ROOT / ".env").items():
        if value is not None:
            os.environ.setdefault(key, value)
    # Parse afresh: a manifest left by an earlier run may predate the models being tested.
    (REPO_ROOT / "transform" / "target-dagster-test" / "manifest.json").unlink(missing_ok=True)
    import orchestration.definitions

    return importlib.reload(orchestration.definitions).defs


@pytest.fixture(scope="session")
def asset_graph(defs):
    return defs.resolve_asset_graph()


def ancestors(graph, key) -> set:
    seen, todo = set(), [key]
    while todo:
        for parent in graph.get(todo.pop()).parent_keys:
            if parent not in seen:
                seen.add(parent)
                todo.append(parent)
    return seen
