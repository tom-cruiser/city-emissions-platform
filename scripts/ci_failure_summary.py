"""Write a Markdown summary of what failed, for the GitHub Actions job summary.

    uv run python scripts/ci_failure_summary.py >> "$GITHUB_STEP_SUMMARY"

Reads whatever exists: reports/pytest.xml (pytest --junitxml) and
transform/target/run_results.json (the last dbt command). Standard library only, so it
also runs when dependency installation was the step that failed.
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTEST_XML = ROOT / "reports" / "pytest.xml"
DBT_RESULTS = ROOT / "transform" / "target" / "run_results.json"
MAX_ROWS = 30


def _cell(text: str, limit: int = 300) -> str:
    text = " ".join((text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pytest_failures(path: Path) -> list[tuple[str, str]]:
    root = ET.parse(path).getroot()
    failed = []
    for case in root.iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is not None:
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            failed.append((name, problem.get("message") or problem.text or ""))
    return failed


def dbt_failures(path: Path) -> list[tuple[str, str, str]]:
    results = json.loads(path.read_text())["results"]
    return [(r["unique_id"], r["status"], r.get("message") or "")
            for r in results if r["status"] in {"error", "fail", "runtime error"}]


def main() -> int:
    out = ["## What failed", ""]
    if PYTEST_XML.exists():
        failed = pytest_failures(PYTEST_XML)
        out += [f"### pytest: {len(failed)} failed", ""]
        if failed:
            out += ["| Test | Message |", "|---|---|"]
            out += [f"| `{_cell(n, 150)}` | {_cell(m)} |" for n, m in failed[:MAX_ROWS]]
            out += [""]
    else:
        out += ["pytest did not run (an earlier step failed).", ""]
    if DBT_RESULTS.exists():
        failed = dbt_failures(DBT_RESULTS)
        out += [f"### dbt: {len(failed)} failed or errored", ""]
        if failed:
            out += ["| Node | Status | Message |", "|---|---|---|"]
            out += [f"| `{_cell(n, 150)}` | {s} | {_cell(m)} |" for n, s, m in failed[:MAX_ROWS]]
            out += [""]
    else:
        out += ["dbt did not run (an earlier step failed).", ""]
    out += [("Full logs: the failed step's log, and the `failure-details` artifact "
             "(pytest.xml, run_results.json, dbt.log, db.log)."), ""]
    sys.stdout.write("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
