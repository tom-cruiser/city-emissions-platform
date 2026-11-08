"""The query enums match the values actually in reporting, so a new EDGAR sector or
pollutant cannot silently become unreachable through the API."""

import pytest

from api.models import EdgarSector, Flag, Pollutant, ReviewStatus, RevisionType, SourceName


@pytest.mark.parametrize(("enum", "sql"), [
    (Pollutant, "select distinct pollutant from reporting.city_emissions"),
    (EdgarSector, "select distinct edgar_sector from reporting.city_emissions"),
    (SourceName, "select distinct source_name from reporting.dataset_versions"),
])
def test_enum_equals_reporting_values(reader_db, enum, sql):
    assert {e.value for e in enum} == {r[0] for r in reader_db.execute(sql)}


def test_flags_cover_every_flag_reporting_can_set(reader_db):
    # Reporting only sets some flags on the sample; the enum must at least contain them,
    # and match the names the dbt model can emit (models/reporting/city_overlap.sql).
    seen = {r[0] for r in reader_db.execute("select distinct unnest(flags) from reporting.city_overlap")}
    assert seen <= {f.value for f in Flag}
    assert {f.value for f in Flag} == {"low_urban_overlap", "suspected_crosswalk_error",
                                       "admin_area_mismatch", "crosswalk_needs_review"}


def test_review_status_and_revision_type_match_the_dbt_accepted_values():
    assert {s.value for s in ReviewStatus} == {"accepted", "needs_review"}
    assert {t.value for t in RevisionType} == {"changed", "added", "removed"}
