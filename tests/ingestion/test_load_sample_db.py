"""Integration tests against warehouse_test. Everything runs in one transaction that is rolled back."""

from ingestion.pipeline import SOURCES, run_sample

ALL_SOURCES = list(SOURCES.values())


def test_sample_load_is_idempotent(db_conn):
    first = run_sample(db_conn, ALL_SOURCES)
    assert first and not any(r.skipped or r.error for r in first)
    # 2 EDGAR files (the synthetic fixture and its revised re-publication, two versions of
    # v2024) + 24 boundary files + 1 GHS-UCDB GeoPackage
    assert len(first) == 27
    rows = {name: sum(r.rows_loaded for r in first if r.source_name == name) for name in ALL_SOURCES}
    assert rows == {"edgar_ucdb": 2 * 27, "geoboundaries": 25, "ghs_ucdb": 25}
    edgar = [r for r in first if r.source_name == "edgar_ucdb"]
    assert [r.source_key for r in edgar] == ["v2024", "v2024"]
    assert edgar[0].dataset_version_id < edgar[1].dataset_version_id  # base first, revised second

    second = run_sample(db_conn, ALL_SOURCES)
    assert all(r.skipped for r in second)  # same bytes -> no new dataset versions
    # A skip reports the version it matched, not None.
    assert [r.dataset_version_id for r in second] == [r.dataset_version_id for r in first]


def test_every_raw_row_traces_to_a_dataset_version(db_conn):
    run_sample(db_conn, ALL_SOURCES)

    versions = db_conn.execute(
        """
        SELECT v.source_name, v.origin, v.file_sha256, v.upstream_sha256, v.downloaded_at,
               coalesce(e.n, 0) + coalesce(g.n, 0) + coalesce(u.n, 0) AS raw_rows, v.row_count
        FROM raw.dataset_versions v
        LEFT JOIN (SELECT dataset_version_id, count(*) n FROM raw.edgar_ucdb_emissions
                   GROUP BY 1) e USING (dataset_version_id)
        LEFT JOIN (SELECT dataset_version_id, count(*) n FROM raw.geoboundaries_features
                   GROUP BY 1) g USING (dataset_version_id)
        LEFT JOIN (SELECT dataset_version_id, count(*) n FROM raw.ghs_ucdb_urban_centres
                   GROUP BY 1) u USING (dataset_version_id)
        """
    ).fetchall()

    assert len(versions) == 27
    for source, origin, sha, upstream_sha, obtained_at, raw_rows, row_count in versions:
        assert raw_rows == row_count > 0  # every version has exactly the rows it claims
        assert len(sha) == 64 and obtained_at is not None
        if source == "edgar_ucdb":
            assert origin == "synthetic" and upstream_sha is None  # never real EDGAR rows
        else:
            assert origin == "sample" and len(upstream_sha) == 64 and upstream_sha != sha

    # And no raw row exists without a version (the FK guarantees it; check anyway).
    orphans = db_conn.execute(
        """
        SELECT count(*) FROM raw.edgar_ucdb_emissions e
        WHERE NOT EXISTS (SELECT 1 FROM raw.dataset_versions v
                          WHERE v.dataset_version_id = e.dataset_version_id)
        """
    ).fetchone()[0]
    assert orphans == 0
