"""Check the figures quoted in README.md and docs/ against the data and the code.

Run by hand, not in CI: most figures need the real warehouse (downloaded data), which CI
never has.

    uv run --env-file .env python scripts/check_readme_numbers.py            # table to stdout
    uv run --env-file .env python scripts/check_readme_numbers.py --markdown # for a PR description

Each check states the figure as the docs quote it, where it is quoted, where the value
comes from, and the value computed now:

- real: the real `warehouse` (downloaded EDGAR, GHS-UCDB and geoBoundaries), as the
  pipeline role
- test: `warehouse_test` after a sample load and `scripts/dbt-build.sh test` (synthetic
  EDGAR), as the test pipeline role
- code: the repository itself (seeds, dbt project, pytest collection, OpenAPI, uv.lock)

Exit status 1 if any figure differs. When a figure changes on purpose, fix the docs and
the expected value here together.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psycopg
from packaging.markers import Marker
from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parent.parent
AFRICA = {"BDI", "COD", "EGY", "ETH", "GHA", "KEN", "NGA", "RWA", "SEN", "TZA", "UGA", "ZAF"}


@dataclass(frozen=True)
class Check:
    figure: str  # as the docs state it
    where: str  # file(s) quoting it
    source: str  # real | test | code
    expected: str
    actual: Callable[[], object]


def connect(target: str) -> psycopg.Connection:
    env = os.environ
    if target == "real":
        db, user, pw = env["POSTGRES_DB"], env["PIPELINE_USER"], env["PIPELINE_PASSWORD"]
    else:
        db, user, pw = env["TEST_POSTGRES_DB"], env["TEST_PIPELINE_USER"], env["TEST_PIPELINE_PASSWORD"]
    return psycopg.connect(host=env.get("PGHOST", "localhost"), port=env.get("POSTGRES_PORT", "5434"),
                           dbname=db, user=user, password=pw, autocommit=True)


_conns: dict[str, psycopg.Connection] = {}


def q(target: str, sql: str):
    """First column of the first row."""
    if target not in _conns:
        _conns[target] = connect(target)
    return _conns[target].execute(sql).fetchone()[0]


def real(sql: str) -> Callable[[], object]:
    return lambda: q("real", sql)


def test(sql: str) -> Callable[[], object]:
    return lambda: q("test", sql)


def run(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=REPO, check=True, capture_output=True, text=True).stdout


# --- code-side counts ---------------------------------------------------------------

def crosswalk() -> list[dict]:
    import csv
    with open(REPO / "transform/seeds/city_crosswalk.csv", newline="") as f:
        return list(csv.DictReader(f))


def dbt_tests() -> list[dict]:
    out = run("uv", "run", "--env-file", ".env", "dbt", "ls", "--resource-type", "test", "-q",
              "--project-dir", "transform", "--profiles-dir", "transform",
              "--output", "json", "--output-keys", "name depends_on")
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def dbt_tests_outside_reporting_and_snapshots() -> int:
    reporting = {p.stem for p in (REPO / "transform/models/reporting").glob("*.sql")}
    n = 0
    for t in dbt_tests():
        nodes = t["depends_on"]["nodes"]
        if any(x.startswith("snapshot.") for x in nodes):
            continue
        if {x.split(".")[-1] for x in nodes} & reporting:
            continue
        n += 1
    return n


def pytest_count(*args: str) -> int:
    out = run("uv", "run", "pytest", "--collect-only", "-q", *args)
    m = re.search(r"(\d+)(?:/\d+)? tests? collected", out)
    return int(m.group(1))


def openapi_data_endpoints() -> int:
    paths = json.loads((REPO / "docs/openapi.json").read_text())["paths"]
    return sum(1 for p in paths if p.startswith("/v1/"))


def api_image_packages() -> int:
    """Packages the API image installs: the lock's api group, for CPython 3.12 on Linux."""
    out = run("uv", "export", "--frozen", "--no-default-groups", "--group", "api",
              "--no-hashes", "--no-emit-project")
    env = {"sys_platform": "linux", "platform_system": "Linux", "implementation_name": "cpython",
           "platform_python_implementation": "CPython", "python_version": "3.12",
           "python_full_version": "3.12.0", "os_name": "posix", "platform_machine": "x86_64"}
    n = 0
    for line in out.splitlines():
        if not re.match(r"[A-Za-z0-9]", line):
            continue
        req = Requirement(line.strip())
        if req.marker is None or Marker(str(req.marker)).evaluate(env):
            n += 1
    return n


def dagster_assets() -> str:
    """Materializable assets in the Dagster code location: total / ingestion group / the rest (dbt)."""
    out = run("uv", "run", "--env-file", ".env", "python", "-c",
              "from orchestration.definitions import defs\n"
              "g = defs.resolve_asset_graph()\n"
              "n = [g.get(k) for k in g.get_all_asset_keys()]\n"
              "m = [x for x in n if x.is_materializable]\n"
              "i = sum(x.group_name == 'ingestion' for x in m)\n"
              "print(f'{len(m)}/{i}/{len(m) - i}')")
    return out.strip().splitlines()[-1]


def sample_geoboundaries_files() -> int:
    return len(list((REPO / "data/sample/geoboundaries").glob("*.geojson")))


def lines_of(path: str) -> int:
    return len((REPO / path).read_text().splitlines())


def synthetic_header_columns() -> int:
    from openpyxl import load_workbook
    wb = load_workbook(next((REPO / "data/sample/edgar").glob("*_SYNTHETIC.xlsx")), read_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=10, values_only=True):
            if row and row[0] == "ID_UC_G0":
                return sum(1 for c in row if c is not None)
    raise RuntimeError("header row not found")


# --- name comparison, as in docs/data-quality.md ---------------------------------------

def _repair(s: str) -> str:
    """Same rule as transform/macros/repair_mojibake.sql: chars back to cp1252 bytes, decode UTF-8."""
    b = bytearray()
    for ch in s:
        try:
            b += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) < 256:  # the five bytes cp1252 leaves undefined
                b.append(ord(ch))
            else:
                return s
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return s


def name_differences() -> tuple[int, int, int, int]:
    """(differing names, of which only EDGAR's '?', real differences, differing countries)."""
    if "real" not in _conns:
        _conns["real"] = connect("real")
    rows = _conns["real"].execute(
        "SELECT e.uc_name, u.uc_name, e.country_name, u.country_name"
        " FROM modelled.stg_edgar__urban_centres e"
        " JOIN modelled.stg_ghs_ucdb__urban_centres u USING (uc_id)").fetchall()
    names = only_q = countries = 0
    for en, un, ec, uc in rows:
        un, uc = un or "", uc or ""  # a few UCDB centres have no name
        countries += ec != _repair(uc)
        u = _repair(un)
        if en == u:
            continue
        names += 1
        pattern = "^" + "".join(".+?" if c == "?" else re.escape(c) for c in en) + "$"
        only_q += "?" in en and re.match(pattern, u) is not None
    return names, only_q, names - only_q, countries


# --- the checks ------------------------------------------------------------------------

OVERLAP = "reporting.city_overlap"
# Largest difference between the overlap share in Mollweide and on the ellipsoid.
MOLLWEIDE_VS_GEODESIC = """
WITH a AS (
    SELECT ST_Transform(d.admin_geom, 54009) AS adm, u.geom AS uc,
           d.admin_geom::geography AS adm_g, ST_Transform(u.geom, 4326)::geography AS uc_g
    FROM modelled.dim_city d JOIN modelled.stg_ghs_ucdb__urban_centres u USING (uc_id))
SELECT max(abs(ST_Area(ST_Intersection(uc, adm)) / ST_Area(uc)
               - ST_Area(ST_Intersection(uc_g, adm_g)) / ST_Area(uc_g)))
FROM a"""

CHECKS = [
    # Cities and coverage
    Check("25 cities", "README, docs/data-quality.md", "code", "25", lambda: len(crosswalk())),
    Check("24 countries", "README, docs/data-quality.md", "code", "24",
          lambda: len({r["country_iso3"] for r in crosswalk()})),
    Check("13 cities in Africa", "README, docs/data-quality.md", "code", "13",
          lambda: sum(r["country_iso3"] in AFRICA for r in crosswalk())),
    Check("12 African countries", "docs/data-quality.md", "code", "12",
          lambda: len({r["country_iso3"] for r in crosswalk()} & AFRICA)),
    Check("official area from Wikipedia for 23 cities", "README, docs/design-notes.md", "code", "23",
          lambda: sum(r["official_area_source"].startswith("Wikipedia infobox") for r in crosswalk())),
    Check("24 geoBoundaries files (sample)", "README, docs/ingestion.md", "code", "24",
          sample_geoboundaries_files),
    Check("24 geoBoundaries files (loaded)", "README, docs/orchestration.md", "real", "24",
          real("SELECT count(*) FROM raw.dataset_versions WHERE source_name = 'geoboundaries'"
               " AND origin = 'download'")),
    # Key findings
    Check("12 of 25 cities low_urban_overlap", "README, docs/transform.md", "real", "12",
          real(f"SELECT count(*) FILTER (WHERE low_urban_overlap) FROM {OVERLAP}")),
    Check("only Accra suspected_crosswalk_error", "README, docs/transform.md", "real", "accra-gha",
          real(f"SELECT string_agg(city_id, ',') FROM {OVERLAP} WHERE suspected_crosswalk_error")),
    Check("Accra share 0.005", "README, docs/transform.md", "real", "0.005",
          real(f"SELECT round(uc_share_inside_admin::numeric, 3) FROM {OVERLAP} WHERE city_id = 'accra-gha'")),
    Check("Paris share 0.074", "docs/transform.md", "real", "0.074",
          real(f"SELECT round(uc_share_inside_admin::numeric, 3) FROM {OVERLAP} WHERE city_id = 'paris-fra'")),
    Check("Jakarta 14% inside DKI Jakarta", "docs/transform.md", "real", "14",
          real(f"SELECT round(100 * uc_share_inside_admin)::int FROM {OVERLAP} WHERE city_id = 'jakarta-idn'")),
    Check("Jakarta 123 Mt CO2e (2022)", "README, docs/transform.md", "real", "123",
          real("SELECT round(latest_urban_centre_ghg_t_co2e / 1e6) FROM reporting.cities"
               " WHERE city_id = 'jakarta-idn'")),
    Check("6 largest emitters all low_urban_overlap", "docs/transform.md", "real", "6",
          real("SELECT count(*) FILTER (WHERE low_urban_overlap) FROM (SELECT low_urban_overlap"
               " FROM reporting.cities ORDER BY latest_urban_centre_ghg_t_co2e DESC LIMIT 6) t")),
    Check("admin_area_mismatch: Accra, Buenos Aires", "README, docs/api.md", "real",
          "accra-gha,buenos-aires-arg",
          real(f"SELECT string_agg(city_id, ',' ORDER BY city_id) FROM {OVERLAP} WHERE admin_area_mismatch")),
    Check("Accra area −72% vs official", "README, docs/transform.md", "real", "-72",
          real(f"SELECT round(100 * admin_area_vs_official)::int FROM {OVERLAP} WHERE city_id = 'accra-gha'")),
    Check("Buenos Aires area +374% vs official", "README, docs/transform.md", "real", "374",
          real(f"SELECT round(100 * admin_area_vs_official)::int FROM {OVERLAP} WHERE city_id = 'buenos-aires-arg'")),
    Check("Accra polygon 5.7 km², official 20.4 km²", "README, docs/data-quality.md", "real", "5.7/20.4",
          real(f"SELECT round(admin_area_km2::numeric, 1) || '/' || official_area_km2 FROM {OVERLAP}"
               " WHERE city_id = 'accra-gha'")),
    Check("Accra urban centre 1,121 km² (source area)", "README, docs/data-quality.md", "real", "1121",
          real("SELECT source_area_km2 FROM modelled.stg_ghs_ucdb__urban_centres WHERE uc_id = 3175")),
    Check("Buenos Aires polygon 948 km², official 200 km²", "README, docs/data-quality.md", "real", "948/200",
          real(f"SELECT round(admin_area_km2) || '/' || official_area_km2 FROM {OVERLAP}"
               " WHERE city_id = 'buenos-aires-arg'")),
    Check("other 23 cities within 13% of official area", "docs/transform.md", "real", "23",
          real(f"SELECT count(*) FROM {OVERLAP} WHERE abs(admin_area_vs_official) <= 0.13")),
    Check("Buenos Aires share 0.40", "docs/data-quality.md", "real", "0.40",
          real(f"SELECT round(uc_share_inside_admin::numeric, 2) FROM {OVERLAP} WHERE city_id = 'buenos-aires-arg'")),
    Check("needs_review: Accra, Buenos Aires", "README, docs/data-quality.md", "code",
          "accra-gha,buenos-aires-arg",
          lambda: ",".join(sorted(r["city_id"] for r in crosswalk() if r["review_status"] == "needs_review"))),
    Check("thresholds 0.5 / 0.01 / 25% used on the real data", "README, ADR 0001", "real", "0.5/0.01/0.25",
          real(f"SELECT string_agg(DISTINCT concat_ws('/', min_urban_overlap::float, suspect_crosswalk_overlap::float,"
               f" admin_area_tolerance::float), ',') FROM {OVERLAP}")),
    Check("EDGAR years 1975–2022", "README, docs/transform.md", "real", "1975-2022",
          real("SELECT min(year) || '-' || max(year) FROM reporting.city_emissions")),
    Check("2 expected dbt warnings on the sample (area, 1% overlap)", "README quick start", "test", "2",
          test(f"SELECT (bool_or(admin_area_mismatch))::int + (bool_or(suspected_crosswalk_error))::int FROM {OVERLAP}")),
    # Urban-centre releases
    Check("EDGAR 11,686 urban centres", "README, docs/data-quality.md", "real", "11686",
          real("SELECT count(*) FROM modelled.stg_edgar__urban_centres")),
    Check("GHS-UCDB V1.2 11,422 urban centres", "README, docs/ingestion.md", "real", "11422",
          real("SELECT count(*) FROM modelled.stg_ghs_ucdb__urban_centres")),
    Check("264 EDGAR-only IDs, 0 UCDB-only", "README, docs/ingestion.md", "real", "264/0",
          real("SELECT (detail->>'edgar_only') || '/' || (detail->>'ucdb_only') FROM raw.load_checks"
               " WHERE check_name = 'id_match_edgar' ORDER BY dataset_version_id DESC LIMIT 1")),
    Check("22 invalid urban-centre polygons", "docs/ingestion.md, docs/transform.md", "real", "22",
          real("SELECT count(*) FILTER (WHERE NOT geom_was_valid) FROM modelled.stg_ghs_ucdb__urban_centres")),
    # Data quality
    Check("775 mis-encoded EDGAR rows", "docs/data-quality.md", "real", "775",
          real("SELECT count(*) FILTER (WHERE name_repaired) FROM modelled.stg_edgar__urban_centres")),
    Check("339 names lost characters to '?'", "docs/data-quality.md", "real", "339",
          real("SELECT count(*) FILTER (WHERE name_lossy) FROM modelled.stg_edgar__urban_centres")),
    Check("608 distinct mis-encoded strings", "docs/transform.md", "real", "608",
          real("SELECT count(DISTINCT s) FROM (SELECT uc_name_source s FROM modelled.stg_edgar__urban_centres"
               " WHERE uc_name_source <> uc_name UNION SELECT country_name_source"
               " FROM modelled.stg_edgar__urban_centres WHERE country_name_source <> country_name) x")),
    Check("192 duplicate (name, country) pairs", "docs/data-quality.md", "real", "192",
          real("SELECT count(*) FROM (SELECT 1 FROM modelled.stg_edgar__urban_centres"
               " GROUP BY uc_name, country_name HAVING count(*) > 1) d")),
    Check("363 names differ EDGAR vs UCDB (320 only '?', 43 real), 1 country",
          "docs/data-quality.md", "real", "363/320/43/1",
          lambda: "/".join(map(str, name_differences()))),
    # Sizes and rows
    Check("EDGAR file ~24 MB", "docs/running.md, ADR 0006", "real", "24",
          real("SELECT round(sum(file_size_bytes) / 1e6) FROM raw.dataset_versions WHERE source_name = 'edgar_ucdb'")),
    Check("geoBoundaries files ~74 MB", "docs/running.md", "real", "74",
          real("SELECT round(sum(file_size_bytes) / 1e6) FROM raw.dataset_versions WHERE source_name = 'geoboundaries'")),
    Check("GHS-UCDB zip 277 MB", "docs/running.md, docs/ingestion.md", "real", "277",
          real("SELECT round(sum(file_size_bytes) / 1e6) FROM raw.dataset_versions WHERE source_name = 'ghs_ucdb'")),
    Check("all downloads ~375 MB", "README, docs/orchestration.md", "real", "375",
          real("SELECT round(sum(file_size_bytes) / 1e6) FROM raw.dataset_versions WHERE origin = 'download'")),
    Check("2.24M urban-centre emission rows", "docs/running.md, docs/transform.md", "real", "2.24",
          real("SELECT round(count(*) / 1e6, 2) FROM modelled.fct_urban_centre_emissions")),
    Check("~6.7k boundary features", "docs/transform.md", "real", "6.7",
          real("SELECT round(count(*) / 1e3, 1) FROM modelled.stg_geoboundaries__boundaries")),
    Check("city_emissions 4,800 rows", "docs/transform.md", "real", "4800",
          real("SELECT count(*) FROM reporting.city_emissions")),
    Check("city_emissions_trend 800 rows", "docs/transform.md", "real", "800",
          real("SELECT count(*) FROM reporting.city_emissions_trend")),
    Check("dataset_versions 26 rows", "docs/transform.md", "real", "26",
          real("SELECT count(*) FROM reporting.dataset_versions")),
    Check("revisions empty on the real warehouse", "docs/transform.md", "real", "0",
          real("SELECT count(*) FROM reporting.city_emission_revisions")),
    Check("Mollweide vs geodesic share ≤ 1.9e-5", "docs/ingestion.md, ADR 0001", "real", "1.9e-05",
          lambda: f"{float(q('real', MOLLWEIDE_VS_GEODESIC)):.1e}"),
    # Test database (synthetic EDGAR)
    Check("3 EDGAR versions in warehouse_test", "docs/testing.md", "test", "3",
          test("SELECT count(*) FROM reporting.dataset_versions WHERE source_name = 'edgar_ucdb'")),
    Check("revisions: 5 changed, 192 removed, 192 added", "docs/testing.md, docs/transform.md", "test",
          "5/192/192",
          test("SELECT concat_ws('/', count(*) FILTER (WHERE revision_type = 'changed'),"
               " count(*) FILTER (WHERE revision_type = 'removed'),"
               " count(*) FILTER (WHERE revision_type = 'added')) FROM reporting.city_emission_revisions")),
    Check("Accra's four flags", "docs/testing.md", "test", "4",
          test(f"SELECT cardinality(flags) FROM {OVERLAP} WHERE city_id = 'accra-gha'")),
    # Code
    Check("7 reporting models", "README, docs/transform.md", "code", "7",
          lambda: len(list((REPO / "transform/models/reporting").glob("*.sql")))),
    Check("9 data endpoints", "README, docs/api.md", "code", "9", openapi_data_endpoints),
    Check("28 Dagster assets it can run (3 ingestion, 25 dbt)", "README", "code", "28/3/25", dagster_assets),
    Check("PostgreSQL 16 + PostGIS 3.5", "README", "code", "16-3.5",
          lambda: re.search(r"image: postgis/postgis:(\S+)", (REPO / "docker-compose.yml").read_text()).group(1)),
    Check("Python 3.12", "README", "code", "3.12",
          lambda: re.search(r'requires-python = "[^0-9]*(3\.\d+)', (REPO / "pyproject.toml").read_text()).group(1)),
    Check("187 dbt tests", "README", "code", "187", lambda: len(dbt_tests())),
    Check("94 dbt tests on seeds, staging, modelled", "docs/transform.md", "code", "94",
          dbt_tests_outside_reporting_and_snapshots),
    Check("186 pytest tests", "README, docs/testing.md", "code", "186", lambda: pytest_count()),
    Check("16 kinds of bad input → 422", "docs/testing.md", "code", "16",
          lambda: pytest_count("-k", "test_bad_parameters_are_422")),
    Check("API image: 24 packages", "README, docs/design-notes.md", "code", "24", api_image_packages),
    Check("GeoPackage reader 125 lines", "README, ADR 0007, docs/design-notes.md", "code", "125", lambda: lines_of("ingestion/gpkg.py")),
    Check("195-column EDGAR header", "docs/ingestion.md", "code", "195", synthetic_header_columns),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markdown", action="store_true", help="print a Markdown table")
    args = ap.parse_args()

    if q("real", "SELECT count(*) FROM raw.dataset_versions WHERE origin <> 'download'") != 0:
        print("The warehouse holds non-downloaded data; real-data figures would be wrong.", file=sys.stderr)
        return 2

    results = []
    for c in CHECKS:
        try:
            got = str(c.actual())
        except Exception as exc:  # noqa: BLE001 - report it; one broken query must not hide the rest
            got = f"error: {exc}".splitlines()[0]
        results.append((c, got, got == c.expected))

    if args.markdown:
        print("| | Figure | Quoted in | Source | Expected | Actual |")
        print("|---|---|---|---|---|---|")
        for c, got, ok in results:
            print(f"| {'✅' if ok else '❌'} | {c.figure} | {c.where} | {c.source} | {c.expected} | {got} |")
    else:
        for c, got, ok in results:
            print(f"{'ok  ' if ok else 'FAIL'} [{c.source:4}] {c.figure}: expected {c.expected}, got {got}")
    bad = sum(not ok for _, _, ok in results)
    print(f"\n{len(results) - bad}/{len(results)} figures match.", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
