"""The code location loads, and the asset graph runs from source file to reporting table."""

import pytest
from dagster import AssetKey, Definitions

from orchestration.resources import pipeline_target
from tests.orchestration.conftest import ancestors

SOURCE_FILES = {AssetKey(["source", s]) for s in ("edgar_ucdb", "geoboundaries", "ghs_ucdb")}
RAW = {AssetKey(["raw", t]) for t in ("edgar_ucdb_emissions", "geoboundaries_features", "ghs_ucdb_urban_centres")}
REPORTING = {"cities", "city_emissions", "city_emissions_trend", "city_boundaries", "city_overlap",
             "dataset_versions", "city_emission_revisions"}


def test_definitions_load(defs):
    Definitions.validate_loadable(defs)


def test_ingestion_assets_are_materializable_and_files_external(asset_graph):
    for key in RAW:
        assert asset_graph.get(key).is_materializable, key
    for key in SOURCE_FILES | {AssetKey(["raw", "dataset_versions"]), AssetKey(["raw", "load_checks"])}:
        assert not asset_graph.get(key).is_materializable, key


def test_every_dbt_source_is_an_ingestion_asset(asset_graph):
    """A renamed raw table or dbt source would silently cut lineage: dagster-dbt would
    invent a new external key instead. Every raw/* key must be one of ours."""
    raw_keys = {k for k in asset_graph.get_all_asset_keys() if k.path[0] == "raw"}
    assert raw_keys == RAW | {AssetKey(["raw", "dataset_versions"]), AssetKey(["raw", "load_checks"])}


def test_reporting_assets_trace_back_to_every_source_file(asset_graph):
    reporting = {k for k in asset_graph.get_all_asset_keys() if k.path[0] == "reporting"}
    assert {k.path[-1] for k in reporting} == REPORTING
    for key in reporting:
        assert asset_graph.get(key).group_name == "reporting"
    # cities draws on all three sources; every reporting table on at least one source file.
    assert SOURCE_FILES | RAW <= ancestors(asset_graph, AssetKey(["reporting", "cities"]))
    for key in reporting:
        assert SOURCE_FILES & ancestors(asset_graph, key), key


def test_ghs_ucdb_loads_after_edgar(asset_graph):
    """Its load check compares urban-centre IDs with the EDGAR version already in raw."""
    assert AssetKey(["raw", "edgar_ucdb_emissions"]) in \
        asset_graph.get(AssetKey(["raw", "ghs_ucdb_urban_centres"])).parent_keys


def test_dbt_tests_are_asset_checks(asset_graph):
    checks = asset_graph.asset_check_keys
    assert any(c.asset_key == AssetKey(["reporting", "cities"]) for c in checks)


def test_snapshots_and_seeds_are_grouped(asset_graph):
    assert asset_graph.get(AssetKey(["modelled", "snap_city_crosswalk"])).group_name == "snapshots"
    assert asset_graph.get(AssetKey(["modelled", "city_crosswalk"])).group_name == "seeds"


def test_pipeline_target(monkeypatch):
    monkeypatch.delenv("PIPELINE_TARGET", raising=False)
    assert pipeline_target() == "warehouse"
    monkeypatch.setenv("PIPELINE_TARGET", "prod")
    with pytest.raises(ValueError, match="PIPELINE_TARGET"):
        pipeline_target()
