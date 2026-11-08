"""Which database the whole graph works on, and connections to it.

PIPELINE_TARGET picks the target for ingestion AND dbt together, so they can never
point at different databases: `warehouse` (default, downloaded data) or `test`
(warehouse_test, the offline sample; used by the tests).
"""

import os
import subprocess

import psycopg
from dagster import ConfigurableResource

from ingestion.config import REPO_ROOT, Settings

TARGETS = ("warehouse", "test")


def pipeline_target() -> str:
    target = os.environ.get("PIPELINE_TARGET", "warehouse")
    if target not in TARGETS:
        raise ValueError(f"PIPELINE_TARGET must be one of {TARGETS}, not {target!r}")
    return target


def git_commit() -> str:
    """GIT_COMMIT by the same rule as scripts/dbt-build.sh: both call scripts/git-commit.sh."""
    return subprocess.run([REPO_ROOT / "scripts" / "git-commit.sh"], capture_output=True,
                          text=True, check=True).stdout.strip()


class Warehouse(ConfigurableResource):
    """A psycopg connection as the pipeline role of the chosen target."""

    target: str

    def connect(self) -> psycopg.Connection:
        # autocommit: each file's load commits in its own `conn.transaction()` block
        # (ingestion/pipeline.py), exactly as the CLI does.
        return psycopg.connect(Settings().dsn(self.target), autocommit=True)
