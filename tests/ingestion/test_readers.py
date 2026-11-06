import pytest
from openpyxl import Workbook, load_workbook

from ingestion import synthetic
from ingestion.config import EDGAR_DATA_SHEET, EDGAR_VARIABLES_SHEET, SAMPLE_DIR
from ingestion.crosswalk import boundary_files_needed, read_crosswalk
from ingestion.edgar import SourceFormatError, read_edgar_workbook
from ingestion.geoboundaries import read_features

EDGAR_FIXTURE = SAMPLE_DIR / "edgar" / synthetic.FILENAME


def test_crosswalk_keys_are_unique():
    rows = read_crosswalk()
    assert len(rows) == 25
    assert len({r["city_id"] for r in rows}) == len(rows)
    assert len({r["edgar_uc_id"] for r in rows}) == len(rows)
    assert len({r["gb_shape_id"] for r in rows}) == len(rows)


def test_boundary_files_are_one_per_country_and_level():
    files = boundary_files_needed()
    assert ("RWA", "ADM1") in files and ("UGA", "ADM2") in files
    assert len(files) == len(set(files)) == 24  # 25 cities in 24 countries (South Africa has two)


def test_synthetic_fixture_is_labelled_synthetic():
    wb = load_workbook(EDGAR_FIXTURE, read_only=True)
    first_line = next(wb["citations and references"].iter_rows(values_only=True))[0]
    assert first_line == "SYNTHETIC DATA - NOT EDGAR"
    assert "SYNTHETIC" in EDGAR_FIXTURE.name


def test_synthetic_fixture_covers_every_crosswalk_city():
    _, rows = read_edgar_workbook(EDGAR_FIXTURE)
    fixture_ids = {r["ID_UC_G0"] for r in rows}
    assert {int(r["edgar_uc_id"]) for r in read_crosswalk()} <= fixture_ids


def test_reads_synthetic_fixture_with_the_real_loader():
    unit, rows = read_edgar_workbook(EDGAR_FIXTURE)
    assert unit == "ton/year"
    assert len(rows) == 27  # 25 crosswalk cities + 2 edge cases
    assert list(rows[0]) == synthetic.header()  # 195 columns, EDGAR v2024 order

    by_id = {r["ID_UC_G0"]: r for r in rows}
    # Mis-encoding is kept exactly as EDGAR publishes it; the modelled layer repairs it.
    assert by_id[7277]["UC_name"] == "SÃ£o Paulo"
    assert by_id[5402]["UC_country"] == "MÃ©xico"
    # Duplicate (name, country): only an ID join tells these apart.
    lagos = [r for r in rows if (r["UC_name"], r["UC_country"]) == ("Lagos", "Nigeria")]
    assert sorted(r["ID_UC_G0"] for r in lagos) == [1289, synthetic.DUPLICATE_NAME_ID]


def test_synthetic_values_are_plausible_in_shape():
    _, rows = read_edgar_workbook(EDGAR_FIXTURE)
    values = [v for r in rows for k, v in r.items() if k.startswith("EMI_")]
    assert all(v >= 0 for v in values)
    for r in rows:  # total GHG (CO2e) includes CO2, so it can never be smaller
        for s in synthetic.SECTORS:
            for y in synthetic.YEARS:
                assert r[f"EMI_GWP_100_AR5_GHG_{s}_{y}"] >= r[f"EMI_CO2_{s}_{y}"]
    uc_id, sector = synthetic.ZERO_SECTOR
    zero_row = next(r for r in rows if r["ID_UC_G0"] == uc_id)
    assert all(v == 0 for k, v in zero_row.items() if f"_{sector}_" in k)


def test_rejects_edgar_file_with_changed_layout(tmp_path):
    wb = Workbook()
    wb.active.title = EDGAR_DATA_SHEET
    wb.active.append(["ID_UC_G0", "UC_country"])  # UC_name missing
    wb.create_sheet(EDGAR_VARIABLES_SHEET).append(["Units", "ton/year"])
    path = tmp_path / "changed.xlsx"
    wb.save(path)

    with pytest.raises(SourceFormatError, match="UC_name"):
        read_edgar_workbook(path)


def test_synthetic_generation_is_reproducible(tmp_path):
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    synthetic.write_synthetic_edgar(a)
    synthetic.write_synthetic_edgar(b)
    assert a.read_bytes() == b.read_bytes() == EDGAR_FIXTURE.read_bytes()


def test_reads_geoboundaries_sample():
    features = read_features(SAMPLE_DIR / "geoboundaries" / "geoBoundaries-RWA-ADM1_simplified.geojson")
    assert [f["properties"]["shapeName"] for f in features] == ["City of Kigali"]
    assert features[0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
