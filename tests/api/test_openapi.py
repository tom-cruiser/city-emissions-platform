"""The OpenAPI document states the urban-centre caveat, and matches the committed
snapshot (docs/openapi.json), so the API contract cannot change by accident.

After an intended change, regenerate the snapshot and commit it with the change:

    UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/api/test_openapi.py
"""

import json
import os

import pytest

from api.docs import URBAN_CENTRE_CAVEAT
from api.main import create_app
from api.settings import REPO_ROOT

SNAPSHOT = REPO_ROOT / "docs" / "openapi.json"


@pytest.fixture(scope="module")
def spec(make_settings) -> dict:
    # Building the document needs no database: the app is never started.
    return create_app(make_settings(db_port=1)).openapi()


def _properties(spec: dict):
    for model, schema in spec["components"]["schemas"].items():
        for name, prop in schema.get("properties", {}).items():
            yield model, name, prop


def test_description_leads_with_the_urban_centre_caveat(spec):
    description = spec["info"]["description"]
    assert "Read this first: urban centre ≠ city" in description
    assert URBAN_CENTRE_CAVEAT in description
    assert "GPC-aligned, not a GPC inventory" in description
    assert "exact `numeric`" in description  # floats in JSON, exact in the warehouse


def test_every_emissions_field_states_the_caveat(spec):
    fields = [(m, n, p) for m, n, p in _properties(spec) if "urban_centre_emissions" in n
              or n == "latest_urban_centre_ghg_t_co2e"]
    assert len(fields) >= 5  # EmissionItem, TrendItem, RevisionItem x2, CitySummary
    missing = [f"{m}.{n}" for m, n, p in fields if URBAN_CENTRE_CAVEAT not in p.get("description", "")]
    assert not missing, missing


def test_territory_basis_is_a_documented_constant(spec):
    prop = spec["components"]["schemas"]["CityContext"]["properties"]["territory_basis"]
    assert prop["const"] == "ghs_urban_centre"
    assert URBAN_CENTRE_CAVEAT in prop["description"]


def test_emissions_tag_repeats_the_caveat(spec):
    tags = {t["name"]: t["description"] for t in spec["tags"]}
    assert URBAN_CENTRE_CAVEAT in tags["emissions"]


def test_spec_matches_the_committed_snapshot(spec):
    rendered = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_OPENAPI_SNAPSHOT") == "1":
        if os.environ.get("CI"):
            pytest.fail("UPDATE_OPENAPI_SNAPSHOT is refused in CI: regenerate locally and commit the snapshot")
        SNAPSHOT.write_text(rendered, encoding="utf-8")
    assert SNAPSHOT.exists(), "no snapshot: run with UPDATE_OPENAPI_SNAPSHOT=1"
    assert SNAPSHOT.read_text(encoding="utf-8") == rendered, (
        "the OpenAPI document changed. If intended: UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest "
        "tests/api/test_openapi.py, then commit docs/openapi.json")
