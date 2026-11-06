"""GHS-UCDB load into warehouse_test: checks recorded, SRID, Mollweide areas, repair path.

Everything runs inside the rolled-back test transaction (see tests/conftest.py).
"""

import pytest

from ingestion import config
from ingestion.crosswalk import read_crosswalk
from ingestion.ghs_ucdb import LoadCheckError
from ingestion.pipeline import SOURCES, run_sample

ALL_SOURCES = list(SOURCES.values())


@pytest.fixture
def loaded(db_conn):
    results = run_sample(db_conn, ALL_SOURCES)
    (ucdb,) = [r for r in results if r.source_name == config.GHS_UCDB_SOURCE_NAME]
    return db_conn, ucdb


def test_esri_54009_is_in_spatial_ref_sys(db_conn):
    row = db_conn.execute(
        "SELECT srid, srtext FROM spatial_ref_sys WHERE auth_name = 'ESRI' AND auth_srid = 54009"
    ).fetchone()
    assert row is not None and row[0] == 54009 and "Mollweide" in row[1]


def test_every_load_check_is_recorded(loaded):
    conn, ucdb = loaded
    checks = dict(conn.execute(
        "SELECT check_name, status FROM raw.load_checks WHERE dataset_version_id = %s",
        (ucdb.dataset_version_id,)).fetchall())
    assert set(checks) == {"row_count", "gpkg_header", "srid", "geometry_type",
                           "geometry_valid", "area_vs_source", "id_match_edgar"}
    for name in ("row_count", "gpkg_header", "srid", "geometry_type", "area_vs_source"):
        assert checks[name] == "pass", name


def test_id_match_reports_the_synthetic_only_ids(loaded):
    conn, ucdb = loaded
    status, detail = conn.execute(
        "SELECT status, detail FROM raw.load_checks WHERE dataset_version_id = %s"
        " AND check_name = 'id_match_edgar'", (ucdb.dataset_version_id,)).fetchone()
    # The synthetic EDGAR file has two invented IDs that no real urban centre has.
    assert status == "warn"
    assert detail["matched"] == 25 and detail["edgar_only_examples"] == [990001, 990002]
    assert detail["ucdb_only"] == 0 and detail["crosswalk_missing_in_ucdb"] == []


def test_geometries_are_stored_unrepaired_in_mollweide(loaded):
    conn, ucdb = loaded
    srids, n = conn.execute(
        "SELECT array_agg(DISTINCT ST_SRID(geom)), count(*) FROM raw.ghs_ucdb_urban_centres"
        " WHERE dataset_version_id = %s", (ucdb.dataset_version_id,)).fetchone()
    assert srids == [54009] and n == 25


def test_make_valid_repairs_every_polygon(loaded):
    """What dbt staging will do: ST_MakeValid, keep the polygonal part."""
    conn, ucdb = loaded
    bad = conn.execute(
        """SELECT count(*) FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s
           AND NOT ST_IsValid(ST_CollectionExtract(ST_MakeValid(geom), 3))""",
        (ucdb.dataset_version_id,)).fetchone()[0]
    assert bad == 0


def test_overlap_share_in_mollweide_matches_geodesic(loaded):
    """Overlap ratios are computed in ESRI:54009 (Stage 3). Check that is safe for our 25 cities.

    PROJ's Mollweide is a spherical projection, so absolute areas are off by up to ~0.7%
    depending on latitude. The error is nearly identical for both polygons of one city, so
    it cancels in the ratio: measured max difference on the real data is ~2e-5.
    """
    conn, ucdb = loaded
    shares = conn.execute(
        """
        WITH cw AS (SELECT * FROM unnest(%s::bigint[], %s::text[]) AS t(uc_id, shape_id)),
        adm AS (SELECT properties->>'shapeID' AS sid,
                       ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry::text), 4326)) AS g
                FROM raw.geoboundaries_features),
        uc AS (SELECT (properties->>'ID_UC_G0')::bigint AS id,
                      ST_CollectionExtract(ST_MakeValid(geom), 3) AS g
               FROM raw.ghs_ucdb_urban_centres WHERE dataset_version_id = %s),
        i AS (SELECT uc.g AS ucg, ST_Intersection(uc.g, ST_Transform(adm.g, 54009)) AS ig, adm.g AS ag
              FROM cw JOIN adm ON adm.sid = cw.shape_id JOIN uc ON uc.id = cw.uc_id)
        SELECT ST_Area(ig) / ST_Area(ucg),
               ST_Area(ST_Transform(ig, 4326)::geography) / ST_Area(ST_Transform(ucg, 4326)::geography),
               abs(ST_Area(ST_Transform(ag, 54009)) / ST_Area(ag::geography) - 1)
        FROM i
        """,
        ([int(r["edgar_uc_id"]) for r in read_crosswalk()], [r["gb_shape_id"] for r in read_crosswalk()],
         ucdb.dataset_version_id)).fetchall()
    assert len(shares) == 25
    for share_mollweide, share_geodesic, abs_area_err in shares:
        assert share_mollweide == pytest.approx(share_geodesic, abs=1e-4)
        assert abs_area_err < 0.01  # absolute areas: use geography, not Mollweide, for km² figures


def test_wrong_srs_fails_before_anything_is_written(db_conn, monkeypatch):
    monkeypatch.setattr(config, "GHS_UCDB_EXPECTED_SRS", ("EPSG", 3857))
    with pytest.raises(LoadCheckError, match="srid"):
        run_sample(db_conn, [config.GHS_UCDB_SOURCE_NAME])
    n = db_conn.execute("SELECT count(*) FROM raw.dataset_versions WHERE source_name = 'ghs_ucdb'").fetchone()[0]
    assert n == 0


def test_check_failing_after_insert_rolls_back_rows_and_version(db_conn, monkeypatch):
    from ingestion import ghs_ucdb

    real = ghs_ucdb.read_crosswalk()
    monkeypatch.setattr(ghs_ucdb, "read_crosswalk", lambda: [*real, {"edgar_uc_id": "999999999"}])
    with pytest.raises(LoadCheckError, match="id_match_edgar"):
        run_sample(db_conn, ALL_SOURCES)
    counts = db_conn.execute(
        """SELECT (SELECT count(*) FROM raw.ghs_ucdb_urban_centres),
                  (SELECT count(*) FROM raw.load_checks),
                  (SELECT count(*) FROM raw.dataset_versions WHERE source_name = 'ghs_ucdb')"""
    ).fetchone()
    assert counts == (0, 0, 0)
