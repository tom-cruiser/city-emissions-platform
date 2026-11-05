import pytest
from openpyxl import Workbook

from ingestion.config import EDGAR_DATA_SHEET, EDGAR_VARIABLES_SHEET, SAMPLE_DIR
from ingestion.crosswalk import boundary_files_needed, read_crosswalk
from ingestion.edgar import SourceFormatError, read_edgar_workbook
from ingestion.geoboundaries import read_features

EDGAR_SAMPLE = SAMPLE_DIR / "edgar" / "EDGAR_emiss_on_UCDB_2024.xlsx"


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


@pytest.mark.skipif(
    not EDGAR_SAMPLE.exists(),
    reason="synthetic EDGAR fixture not created yet (real EDGAR rows are not committed: licence)",
)
def test_reads_edgar_sample_unchanged():
    unit, rows = read_edgar_workbook(EDGAR_SAMPLE)
    assert unit == "ton/year"
    assert len(rows) == 25
    kigali = next(r for r in rows if r["ID_UC_G0"] == 597)
    assert kigali["UC_name"] == "Kigali"
    # Raw keeps the source's own encoding damage; the modelled layer repairs it.
    assert next(r for r in rows if r["ID_UC_G0"] == 7277)["UC_name"] == "SÃ£o Paulo"


def test_rejects_edgar_file_with_changed_layout(tmp_path):
    wb = Workbook()
    wb.active.title = EDGAR_DATA_SHEET
    wb.active.append(["ID_UC_G0", "UC_country"])  # UC_name missing
    wb.create_sheet(EDGAR_VARIABLES_SHEET).append(["Units", "ton/year"])
    path = tmp_path / "changed.xlsx"
    wb.save(path)

    with pytest.raises(SourceFormatError, match="UC_name"):
        read_edgar_workbook(path)


def test_reads_geoboundaries_sample():
    features = read_features(SAMPLE_DIR / "geoboundaries" / "geoBoundaries-RWA-ADM1_simplified.geojson")
    assert [f["properties"]["shapeName"] for f in features] == ["City of Kigali"]
    assert features[0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
