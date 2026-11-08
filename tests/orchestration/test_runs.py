"""Runs of the weekly job, in process, against warehouse_test with the offline sample.

The sample is already loaded (CI and local setups load it before dbt), so the loads are
skipped by SHA-256 and nothing new is written to raw; dbt rebuilds warehouse_test.
"""

import os

import httpx
import psycopg
import pytest
from dagster import AssetKey, Failure, RetryRequested, build_asset_context, instance_for_test

import orchestration.ingestion as ingestion_assets
from ingestion.versioning import LoadResult
from orchestration.resources import Warehouse, git_commit
from tests.conftest import TEST_DB

RAW_STEPS = ["raw__edgar_ucdb_emissions", "raw__geoboundaries_features", "raw__ghs_ucdb_urban_centres"]
SAMPLE = {"ops": {step: {"config": {"mode": "sample"}} for step in RAW_STEPS}}


@pytest.fixture
def run_weekly(defs, sample_loaded):
    def run():
        with instance_for_test() as instance:
            return defs.resolve_job_def("weekly_refresh").execute_in_process(
                run_config=SAMPLE, instance=instance, raise_on_error=False)
    return run


@pytest.fixture
def sample_loaded():
    """The sample must already be in warehouse_test, so the loads are no-ops.

    Not the db_conn fixture: its open transaction holds a TRUNCATE lock on raw, which
    would block the job's own connections.
    """
    try:
        conn = psycopg.connect(TEST_DB.dsn, connect_timeout=3)
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"test database unreachable: {exc}")
        pytest.skip(f"test database unreachable: {exc}")
    with conn:
        if not conn.execute("select count(*) from raw.dataset_versions").fetchone()[0]:
            pytest.fail("warehouse_test has no sample: run `python -m ingestion load --mode sample --target test`")


def steps(result, event_type: str) -> set[str]:
    return {e.step_key for e in result.all_events if e.event_type_value == event_type}


def test_weekly_job_end_to_end_on_the_sample(run_weekly, monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    result = run_weekly()
    assert result.success
    assert steps(result, "STEP_SUCCESS") >= {*RAW_STEPS, "dbt_models"}
    materialized = {e.asset_key for e in result.get_asset_materialization_events()}
    assert {AssetKey(["raw", "edgar_ucdb_emissions"]), AssetKey(["reporting", "cities"]),
            AssetKey(["modelled", "snap_city_crosswalk"])} <= materialized
    edgar = result.asset_materializations_for_node("raw__edgar_ucdb_emissions")[0]
    assert edgar.metadata["mode"].value == "sample"
    assert edgar.metadata["files_failed"].value == 0
    assert edgar.metadata["files_already_loaded"].value == 3  # SHA-256: no duplicates
    # dbt ran with the shared GIT_COMMIT rule: the step sets it in the environment that
    # dagster-dbt hands to the dbt subprocess (in process here, so it is visible).
    assert os.environ["GIT_COMMIT"] == git_commit()
    # The load-check warnings check ran on every raw asset (pass or WARN, never an error).
    evaluations = {e.event_specific_data.asset_check_key.asset_key.path[1]
                   for e in result.all_events if e.event_type_value == "ASSET_CHECK_EVALUATION"}
    assert {"edgar_ucdb_emissions", "geoboundaries_features", "ghs_ucdb_urban_centres"} <= evaluations


def test_failed_source_skips_dbt(run_weekly, monkeypatch):
    real = ingestion_assets.run_sample

    def one_country_fails(conn, sources):
        if sources == ["geoboundaries"]:
            return [LoadResult("geoboundaries", "RWA_ADM1", 101, 0, skipped=True),
                    LoadResult("geoboundaries", "SEN_ADM1", None, 0, skipped=False, error="HTTPStatusError: 404")]
        return real(conn, sources)

    monkeypatch.setattr(ingestion_assets, "run_sample", one_country_fails)
    result = run_weekly()

    assert not result.success
    assert "raw__geoboundaries_features" in steps(result, "STEP_FAILURE")
    assert {"raw__edgar_ucdb_emissions", "raw__ghs_ucdb_urban_centres"} <= steps(result, "STEP_SUCCESS")
    assert "dbt_models" not in steps(result, "STEP_START")
    failure = next(e for e in result.all_events if e.event_type_value == "STEP_FAILURE")
    assert "1 of 2 geoboundaries file(s) failed: SEN_ADM1: HTTPStatusError: 404" in str(failure.event_specific_data)


def test_network_error_is_retried(defs, monkeypatch):
    def offline(conn, sources):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(ingestion_assets, "run_download", offline)
    warehouse = Warehouse(target="warehouse")
    monkeypatch.setattr(Warehouse, "connect", lambda self: _NullConn())
    with pytest.raises(RetryRequested) as exc:
        ingestion_assets.load_source(build_asset_context(), warehouse, "download", "edgar_ucdb")
    assert exc.value.max_retries == ingestion_assets.DOWNLOAD_RETRIES


def test_download_refused_on_test_target(defs):
    with pytest.raises(Failure, match="download mode is refused on the test target"):
        ingestion_assets.load_source(build_asset_context(), Warehouse(target="test"), "download", "edgar_ucdb")


class _NullConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
