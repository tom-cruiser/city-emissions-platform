"""scripts/git-commit.sh: the one GIT_COMMIT rule used by dbt-build.sh and Dagster."""

import os
import re
import subprocess

from ingestion.config import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "git-commit.sh"


def run(**env: str) -> str:
    base = {k: v for k, v in os.environ.items() if k != "GIT_COMMIT"}
    return subprocess.run([SCRIPT], env=base | env, capture_output=True, text=True, check=True).stdout.strip()


def test_preset_value_wins():
    assert run(GIT_COMMIT="0123abc") == "0123abc"


def test_defaults_to_head():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    assert re.fullmatch(re.escape(head) + "(-dirty)?", run())


def test_dbt_build_script_uses_it():
    assert "scripts/git-commit.sh" in (REPO_ROOT / "scripts" / "dbt-build.sh").read_text()


def test_dagster_uses_it(monkeypatch):
    from orchestration.resources import git_commit

    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert git_commit() == run()
    monkeypatch.setenv("GIT_COMMIT", "0123abc")
    assert git_commit() == "0123abc"
