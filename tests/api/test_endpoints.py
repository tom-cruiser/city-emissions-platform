"""Endpoints against warehouse_test (sample load + scripts/dbt-build.sh test).

The sample is known: 25 cities; Accra and Buenos Aires flagged; three synthetic EDGAR
versions whose revisions are 5 changed cells plus Dakar removed and added back
(ingestion/synthetic.py)."""

import pytest

CITY_ENDPOINTS = ["", "/emissions", "/trend", "/revisions", "/overlap", "/boundary"]
CONTEXT_KEYS = {"city_id", "city_name", "country_iso3", "territory_basis", "uc_share_inside_admin",
                "low_urban_overlap", "suspected_crosswalk_error", "admin_area_mismatch",
                "crosswalk_review_status", "flags", "versions"}


def _context(body: dict) -> dict:
    return body if "territory_basis" in body else body["city"]


# --- labels and lineage reach the user ---


@pytest.mark.parametrize("suffix", CITY_ENDPOINTS)
@pytest.mark.parametrize("city_id", ["accra-gha", "kigali-rwa"])
def test_every_city_response_carries_labels_flags_and_versions(client, city_id, suffix):
    r = client.get(f"/v1/cities/{city_id}{suffix}")
    assert r.status_code == 200
    ctx = _context(r.json())
    assert CONTEXT_KEYS <= ctx.keys()
    assert ctx["city_id"] == city_id
    assert ctx["territory_basis"] == "ghs_urban_centre"
    for source, version_id in ctx["versions"].items():
        d = client.get(f"/v1/datasets/{version_id}")
        assert d.status_code == 200, (source, version_id)
        assert d.json()["is_current"] is True


def test_every_city_in_the_list_carries_labels(client):
    items = client.get("/v1/cities?limit=100").json()["items"]
    assert len(items) == 25
    assert all(CONTEXT_KEYS <= i.keys() and i["territory_basis"] == "ghs_urban_centre" for i in items)


def test_accra_is_flagged(client):
    c = client.get("/v1/cities/accra-gha").json()
    assert c["suspected_crosswalk_error"] and c["low_urban_overlap"] and c["admin_area_mismatch"]
    assert c["crosswalk_review_status"] == "needs_review"
    assert set(c["flags"]) == {"low_urban_overlap", "suspected_crosswalk_error",
                               "admin_area_mismatch", "crosswalk_needs_review"}


# --- values equal the reporting tables ---


def test_emissions_equal_the_table(client, reader_db):
    body = client.get("/v1/cities/kigali-rwa/emissions?pollutant=GHG&limit=100").json()
    rows = reader_db.execute(
        "select year, edgar_sector, urban_centre_emissions from reporting.city_emissions "
        "where city_id = 'kigali-rwa' and pollutant = 'GHG' order by year, edgar_sector").fetchall()
    assert body["total"] == len(rows) == 48  # 6 sectors x 8 years
    assert [(i["year"], i["edgar_sector"], i["urban_centre_emissions"]) for i in body["items"]] == \
           [(y, s, float(v)) for y, s, v in rows]
    assert body["unit"] == "t CO2e/yr" and body["is_ghg_total"] is True


def test_trend_equals_the_table(client, reader_db):
    body = client.get("/v1/cities/nairobi-ken/trend?pollutant=CO2").json()
    rows = reader_db.execute(
        "select year, prev_year, urban_centre_emissions, annualised_change_pct from reporting.city_emissions_trend "
        "where city_id = 'nairobi-ken' and pollutant = 'CO2' order by year").fetchall()
    assert [(i["year"], i["prev_year"], i["urban_centre_emissions"], i["annualised_change_pct"])
            for i in body["items"]] == [(y, p, float(v), a) for y, p, v, a in rows]
    assert body["items"][0]["prev_year"] is None and body["unit"] == "t CO2/yr"


def test_overlap_equals_the_table(client, reader_db):
    body = client.get("/v1/cities/paris-fra/overlap").json()
    share, iou = reader_db.execute(
        "select uc_share_inside_admin, iou from reporting.city_overlap where city_id = 'paris-fra'").fetchone()
    assert body["city"]["uc_share_inside_admin"] == share and body["iou"] == iou
    assert body["thresholds"] == {"min_urban_overlap": 0.5, "suspect_crosswalk_overlap": 0.01,
                                  "admin_area_tolerance": 0.25}


# --- revisions: the three synthetic versions ---


def test_revisions_show_changed_removed_and_added(client):
    def total(city, **params):
        return client.get(f"/v1/cities/{city}/revisions", params=params).json()["total"]

    assert total("dakar-sen", revision_type="removed") == 192
    assert total("dakar-sen", revision_type="added") == 192
    assert total("dakar-sen", revision_type="changed") == 0
    assert total("kigali-rwa") == 2 and total("nairobi-ken") == 2 and total("lagos-nga") == 1
    assert total("paris-fra") == 0

    kigali = client.get("/v1/cities/kigali-rwa/revisions", params={"pollutant": "CO2"}).json()["items"]
    assert [(i["edgar_sector"], i["year"], i["revision_type"]) for i in kigali] == [("Transport", 2022, "changed")]
    assert kigali[0]["to_urban_centre_emissions"] / kigali[0]["from_urban_centre_emissions"] == pytest.approx(1.25)
    assert kigali[0]["from_edgar_version_id"] < kigali[0]["to_edgar_version_id"]


def test_datasets_list_three_edgar_versions_one_current(client):
    edgar = client.get("/v1/datasets", params={"source_name": "edgar_ucdb"}).json()
    assert edgar["total"] == 3
    assert [i["is_current"] for i in edgar["items"]] == [False, False, True]
    assert all(i["origin"] == "synthetic" for i in edgar["items"])
    assert client.get("/v1/datasets", params={"is_current": "true"}).json()["total"] == 26


# --- pagination and filters ---


def test_pages_join_up_to_the_full_list(client):
    full = client.get("/v1/cities?limit=100").json()
    pages, offset = [], 0
    while True:
        page = client.get(f"/v1/cities?limit=7&offset={offset}").json()
        assert page["total"] == full["total"] == 25 and page["limit"] == 7 and page["offset"] == offset
        if not page["items"]:
            break
        pages += page["items"]
        offset += 7
    assert pages == full["items"]
    assert [c["city_id"] for c in pages] == sorted(c["city_id"] for c in pages)


def test_emissions_pages_join_up(client):
    full = client.get("/v1/cities/lagos-nga/emissions?limit=100").json()["items"]
    paged = [i for off in (0, 20, 40) for i in
             client.get(f"/v1/cities/lagos-nga/emissions?limit=20&offset={off}").json()["items"]]
    assert paged == full and len(full) == 48


@pytest.mark.parametrize(("query", "expected"), [
    ("country=RWA", {"kigali-rwa"}),
    ("country=ZAF", {"johannesburg-zaf", "cape-town-zaf"}),
    ("flag=suspected_crosswalk_error", {"accra-gha"}),
    ("review_status=needs_review", {"accra-gha", "buenos-aires-arg"}),
    ("flag=admin_area_mismatch&flag=suspected_crosswalk_error", {"accra-gha"}),
    ("country=RWA&review_status=needs_review", set()),
])
def test_city_filters(client, query, expected):
    body = client.get(f"/v1/cities?{query}&limit=100").json()
    assert {c["city_id"] for c in body["items"]} == expected and body["total"] == len(expected)


def test_emission_filters(client):
    body = client.get("/v1/cities/kigali-rwa/emissions",
                      params={"pollutant": "PM2.5", "sector": ["Transport", "Energy"], "year_from": 2020}).json()
    assert body["unit"] == "t/yr" and body["is_ghg_total"] is False
    assert {(i["edgar_sector"], i["year"]) for i in body["items"]} == \
           {(s, y) for s in ("Energy", "Transport") for y in (2020, 2022)}


def test_filtered_out_page_still_has_unit_and_context(client):
    body = client.get("/v1/cities/kigali-rwa/emissions", params={"year_from": 2099}).json()
    assert body["items"] == [] and body["total"] == 0
    assert body["unit"] == "t CO2e/yr" and body["city"]["territory_basis"] == "ghs_urban_centre"


# --- geometry ---


def test_boundary_is_geojson(client):
    r = client.get("/v1/cities/accra-gha/boundary")
    assert r.headers["content-type"].startswith("application/geo+json")
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert [f["id"] for f in fc["features"]] == ["administrative_boundary", "urban_centre"]
    west, south, east, north = fc["bbox"]
    for f in fc["features"]:
        assert f["geometry"]["type"] == "MultiPolygon" and f["properties"]["license"]
        points = [pt for poly in f["geometry"]["coordinates"] for ring in poly for pt in ring]
        assert all(west <= x <= east and south <= y <= north for x, y in points)


# --- errors ---


@pytest.mark.parametrize("suffix", CITY_ENDPOINTS)
def test_unknown_city_is_404(client, suffix):
    r = client.get(f"/v1/cities/no-such-city{suffix}")
    assert r.status_code == 404
    assert r.json() == {"detail": "city 'no-such-city' not found", "code": "city_not_found"}


def test_unknown_dataset_is_404(client):
    r = client.get("/v1/datasets/999999999")
    assert r.status_code == 404 and r.json()["code"] == "dataset_version_not_found"


@pytest.mark.parametrize("url", [
    "/v1/cities/Kigali-RWA",                       # malformed id (uppercase)
    "/v1/cities/kigali_rwa/emissions",             # malformed id (underscore)
    "/v1/cities?limit=0",
    "/v1/cities?limit=101",
    "/v1/cities?offset=-1",
    "/v1/cities?country=rw",
    "/v1/cities?flag=unknown_flag",
    "/v1/cities?review_status=maybe",
    "/v1/cities/kigali-rwa/emissions?pollutant=CH4",
    "/v1/cities/kigali-rwa/emissions?sector=Aviation",
    "/v1/cities/kigali-rwa/emissions?year_from=2020&year_to=1990",
    "/v1/cities/kigali-rwa/trend?year_from=1800",
    "/v1/cities/kigali-rwa/revisions?revision_type=edited",
    "/v1/datasets/0",
    "/v1/datasets/abc",
    "/v1/datasets?source_name=climate_trace",
])
def test_bad_parameters_are_422(client, url):
    r = client.get(url)
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], list)  # FastAPI's standard validation body


def test_data_endpoint_is_503_when_the_database_is_down(make_settings):
    from fastapi.testclient import TestClient

    from api.main import create_app
    with TestClient(create_app(make_settings(db_port=1))) as c:
        r = c.get("/v1/cities/kigali-rwa/emissions")
    assert r.status_code == 503 and r.json()["code"] == "database_unavailable"
