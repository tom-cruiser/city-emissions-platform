"""Static checks on .github/workflows/ci.yml, so the guarantees the README states about CI
cannot be edited away unnoticed."""

import re

import yaml

from ingestion.config import REPO_ROOT

WORKFLOW = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())
TEST = WORKFLOW["jobs"]["test"]
RUNS = "\n".join(step.get("run", "") for step in TEST["steps"])


def test_runs_on_pushes_and_pull_requests_to_main():
    on = WORKFLOW[True]  # YAML 1.1 reads the key `on` as the boolean True
    assert on["push"]["branches"] == ["main"] and on["pull_request"]["branches"] == ["main"]


def test_database_tests_fail_instead_of_skipping():
    assert TEST["env"]["REQUIRE_TEST_DB"] == "1"


def test_git_commit_comes_from_github_sha():
    assert TEST["env"]["GIT_COMMIT"] == "${{ github.sha }}"


def test_steps_run_in_order():
    order = ["uv sync --locked", "ruff check", "docker compose up -d --wait db",
             "ingestion load --mode sample --target test", "--target warehouse",
             "scripts/dbt-build.sh test", "pytest", "git diff --exit-code"]
    positions = [RUNS.index(cmd) for cmd in order]
    assert positions == sorted(positions)


def test_api_image_is_built_but_not_pushed():
    build = next(s for s in WORKFLOW["jobs"]["api-image"]["steps"] if "build-push-action" in s.get("uses", ""))
    assert build["with"]["push"] is False and build["with"]["file"] == "api/Dockerfile"


def test_every_action_is_pinned_to_a_commit_sha():
    uses = [s["uses"] for job in WORKFLOW["jobs"].values() for s in job["steps"] if "uses" in s]
    unpinned = [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)]
    assert uses and not unpinned, unpinned
