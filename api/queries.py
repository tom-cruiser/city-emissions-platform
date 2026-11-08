"""Every SQL statement the API runs. Each reads ONE table in `reporting`, built for its
endpoint by dbt; the API never joins, aggregates or calls PostGIS. Parameters are always
bound (:name), never formatted into the SQL."""

CONTEXT_COLUMNS = """
    city_id, city_name, country_iso3, territory_basis, uc_share_inside_admin,
    low_urban_overlap, suspected_crosswalk_error, admin_area_mismatch,
    crosswalk_review_status, flags, edgar_version_id, ucdb_version_id, gb_version_id
"""
SUMMARY_COLUMNS = CONTEXT_COLUMNS + """,
    uc_id, edgar_uc_name, gb_adm_level, gb_shape_name, match_note, first_year, last_year,
    latest_urban_centre_ghg_t_co2e
"""

# --- cities: filters are all optional (null = no filter) ---
CITIES_WHERE = """
    where (cast(:countries as text[]) is null or country_iso3 = any(:countries))
      and (cast(:review_status as text) is null or crosswalk_review_status = :review_status)
      and (cast(:flags as text[]) is null or flags @> cast(:flags as text[]))
"""
CITIES_PAGE = f"select {SUMMARY_COLUMNS} from reporting.cities {CITIES_WHERE} order by city_id limit :limit offset :offset"
CITIES_COUNT = f"select count(*) as n from reporting.cities {CITIES_WHERE}"
CITY = f"select {SUMMARY_COLUMNS} from reporting.cities where city_id = :city_id"

# --- emissions ---
EMISSIONS_WHERE = """
    where city_id = :city_id and pollutant = :pollutant
      and (cast(:sectors as text[]) is null or edgar_sector = any(:sectors))
      and (cast(:year_from as integer) is null or year >= :year_from)
      and (cast(:year_to as integer) is null or year <= :year_to)
"""
EMISSIONS_PAGE = f"""
    select year, edgar_sector, gpc_sector_code, gpc_sector, mapping_quality,
           sector_mapping_review_status, urban_centre_emissions
    from reporting.city_emissions {EMISSIONS_WHERE}
    order by year, edgar_sector limit :limit offset :offset
"""
EMISSIONS_COUNT = f"select count(*) as n from reporting.city_emissions {EMISSIONS_WHERE}"
# Unit of a pollutant, independent of filters (a filtered page may be empty).
POLLUTANT_UNIT = "select unit, is_ghg_total from reporting.city_emissions where pollutant = :pollutant limit 1"

TREND = """
    select year, prev_year, urban_centre_emissions, change_since_prev_pct, annualised_change_pct,
           sector_count, unit
    from reporting.city_emissions_trend
    where city_id = :city_id and pollutant = :pollutant
      and (cast(:year_from as integer) is null or year >= :year_from)
      and (cast(:year_to as integer) is null or year <= :year_to)
    order by year
"""

REVISIONS_WHERE = """
    where city_id = :city_id
      and (cast(:revision_type as text) is null or revision_type = :revision_type)
      and (cast(:pollutant as text) is null or pollutant = :pollutant)
"""
REVISIONS_PAGE = f"""
    select pollutant, unit, edgar_sector, year, revision_type, from_edgar_version_id,
           to_edgar_version_id, from_urban_centre_emissions, to_urban_centre_emissions,
           change, change_pct
    from reporting.city_emission_revisions {REVISIONS_WHERE}
    order by from_edgar_version_id, to_edgar_version_id, pollutant_code, edgar_sector, year
    limit :limit offset :offset
"""
REVISIONS_COUNT = f"select count(*) as n from reporting.city_emission_revisions {REVISIONS_WHERE}"

# --- geometry ---
OVERLAP = """
    select admin_share_covered, iou, uc_area_km2, admin_area_km2, intersection_area_km2,
           official_area_km2, admin_area_vs_official, min_urban_overlap,
           suspect_crosswalk_overlap, admin_area_tolerance, match_note
    from reporting.city_overlap where city_id = :city_id
"""
BOUNDARY = """
    select gb_shape_id, gb_shape_name, gb_adm_level, boundary_geojson, urban_centre_geojson, bbox,
           admin_area_km2, official_area_km2, boundary_license, boundary_source_url,
           urban_centre_license, gb_version_id, ucdb_version_id
    from reporting.city_boundaries where city_id = :city_id
"""

# --- lineage ---
DATASETS_WHERE = """
    where (cast(:source_name as text) is null or source_name = :source_name)
      and (cast(:is_current as boolean) is null or is_current = :is_current)
"""
DATASET_COLUMNS = """
    dataset_version_id, source_name, source_key, origin, is_current, source_url, file_sha256,
    license, downloaded_at, loaded_at, row_count, load_check_warnings
"""
DATASETS_PAGE = (f"select {DATASET_COLUMNS} from reporting.dataset_versions {DATASETS_WHERE} "
                 "order by dataset_version_id limit :limit offset :offset")
DATASETS_COUNT = f"select count(*) as n from reporting.dataset_versions {DATASETS_WHERE}"
DATASET = f"select {DATASET_COLUMNS} from reporting.dataset_versions where dataset_version_id = :id"
