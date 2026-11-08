"""The weekly schedule, the freshness policy and the load-check-warnings checks."""

from datetime import timedelta

from dagster import AssetKey, DefaultScheduleStatus

from orchestration.checks import CURRENT_WARNINGS_SQL, ORIGINS

RAW = [AssetKey(["raw", t]) for t in ("edgar_ucdb_emissions", "geoboundaries_features", "ghs_ucdb_urban_centres")]


def test_weekly_schedule_is_off_by_default(defs):
    schedule = defs.resolve_schedule_def("weekly_refresh_schedule")
    assert schedule.default_status == DefaultScheduleStatus.STOPPED  # never downloads unasked
    assert schedule.cron_schedule == "0 3 * * 1"
    assert schedule.execution_timezone == "UTC"
    assert schedule.job_name == "weekly_refresh"
    assert len(defs.schedules) == 1
    assert not defs.sensors


def test_weekly_job_covers_every_materializable_asset(defs, asset_graph):
    job = defs.resolve_job_def("weekly_refresh")
    materializable = {k for k in asset_graph.get_all_asset_keys() if asset_graph.get(k).is_materializable}
    assert set(job.asset_layer.selected_asset_keys) == materializable


def test_freshness_policy_on_reporting_only(asset_graph):
    for key in asset_graph.get_all_asset_keys():
        policy = asset_graph.get(key).freshness_policy
        if key.path[0] == "reporting":
            assert policy is not None and policy.fail_window.to_timedelta() == timedelta(days=8), key
        else:
            assert policy is None, key


def test_load_check_warnings_on_every_raw_asset(asset_graph):
    checks = {c for c in asset_graph.asset_check_keys if c.name == "load_check_warnings"}
    assert {c.asset_key for c in checks} == set(RAW)
    for check in checks:
        assert not asset_graph.get_check_spec(check).blocking


def test_load_check_warnings_reads_current_versions_only(db_conn):
    """A warning on a superseded version is not reported; one on the current version is."""
    def add_version(sha: str, loaded_at: str) -> int:
        return db_conn.execute(
            "insert into raw.dataset_versions (source_name, source_key, origin, source_url, file_path,"
            " file_sha256, file_size_bytes, downloaded_at, loaded_at, row_count)"
            " values ('geoboundaries', 'RWA_ADM1', 'sample', 'u', 'p', %s, 1, now(), %s, 1)"
            " returning dataset_version_id", (sha * 64, loaded_at)).fetchone()[0]

    def warn(version: int, name: str) -> None:
        db_conn.execute("insert into raw.load_checks values (%s, %s, 'warn', '{}')", (version, name))

    old = add_version("a", "2026-01-01")
    warn(old, "old_warning")
    params = {"source_name": "geoboundaries", "origins": ORIGINS["test"]}
    new = add_version("b", "2026-02-01")
    assert db_conn.execute(CURRENT_WARNINGS_SQL, params).fetchall() == []
    warn(new, "geometry_valid")
    assert db_conn.execute(CURRENT_WARNINGS_SQL, params).fetchall() == [("RWA_ADM1", new, "geometry_valid", "{}")]
    # The real warehouse's check ignores sample/synthetic origins, as staging does.
    assert db_conn.execute(CURRENT_WARNINGS_SQL, {**params, "origins": ORIGINS["warehouse"]}).fetchall() == []


def test_origins_mirror_the_dbt_macro():
    from ingestion.config import REPO_ROOT

    macro = (REPO_ROOT / "transform" / "macros" / "raw_origins.sql").read_text()
    assert "['sample', 'synthetic'] if target.name == 'test' else ['download']" in macro
    assert ORIGINS == {"warehouse": ["download"], "test": ["sample", "synthetic"]}
