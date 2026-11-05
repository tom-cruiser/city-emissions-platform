"""Integration tests against Postgres. Everything runs in one transaction that is rolled back.

The committed sample currently holds geoBoundaries only; the synthetic EDGAR fixture
is pending (see README, "Stage 2 status"), so EDGAR is covered by reader tests for now.
"""

from ingestion.pipeline import SOURCES, run_sample

ALL_SOURCES = list(SOURCES.values())


def test_sample_load_is_idempotent(db_conn):
    first = run_sample(db_conn, ALL_SOURCES)
    assert first and not any(r.skipped or r.error for r in first)
    assert len(first) == 24  # one boundary file per country
    assert sum(r.rows_loaded for r in first) == 25  # 25 cities (South Africa has two)

    second = run_sample(db_conn, ALL_SOURCES)
    assert all(r.skipped for r in second)  # same bytes -> no new dataset versions


def test_every_raw_row_traces_to_a_dataset_version(db_conn):
    results = run_sample(db_conn, ALL_SOURCES)
    version_ids = [r.dataset_version_id for r in results]

    rows = db_conn.execute(
        """
        SELECT v.origin, v.file_sha256, v.upstream_sha256, v.downloaded_at, count(f.*)
        FROM raw.dataset_versions v
        JOIN raw.geoboundaries_features f USING (dataset_version_id)
        WHERE v.dataset_version_id = ANY(%s)
        GROUP BY 1, 2, 3, 4
        """,
        (version_ids,),
    ).fetchall()

    assert len(rows) == 24  # every version has rows, every row has a version
    assert sum(n for *_, n in rows) == 25
    for origin, sha, upstream_sha, downloaded_at, _ in rows:
        assert origin == "sample"
        assert len(sha) == 64 and len(upstream_sha) == 64 and sha != upstream_sha
        assert downloaded_at is not None
