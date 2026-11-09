# Cities and data quality

The crosswalk and every data-quality finding so far. Back to the [README](../README.md).

## City matching (crosswalk)

The platform covers **25 cities in 24 countries; 13 of the cities, in 12 countries, are in Africa**:
Kigali, Nairobi, Lagos, Bujumbura, Kampala, Addis Ababa, Dar es Salaam, Accra,
Johannesburg, Cape Town, Dakar, Kinshasa, Cairo, Buenos Aires, Mexico City, Bogotá,
Lima, Delhi, Jakarta, Bangkok, Seoul, Tokyo, Berlin, Paris, São Paulo.

`transform/seeds/city_crosswalk.csv` maps each city to an EDGAR urban-centre ID
(`edgar_uc_id`) and a geoBoundaries shape (`gb_shape_id`). Every row also has:

- `match_note`: why this unit was chosen and anything known to be wrong with it.
- `review_status`: `accepted` (unit choice documented, no known problem) or
  `needs_review` (a known problem that a person has to resolve). `accepted` is an
  engineering judgement. No city GHG inventory specialist has reviewed the list yet.

Two cities are `needs_review`: **Accra** and **Buenos Aires**. In both the unit is right
but geoBoundaries' polygon for it is not (see [data quality](#data-quality-findings-so-far)).

The join is by ID and never by name, because names in these sources are unreliable:

- EDGAR has **192 duplicate (name, country) pairs**.
- Spellings differ: `Dar es-Salaam`, and Delhi's urban centre is `Ghaziabad [New Delhi]`.
- The obvious admin match can be wrong. geoBoundaries' UK ADM2 has *City of London*,
  the 2.9 km² financial district, not Greater London (33 boroughs). London is therefore
  **excluded** rather than silently mismatched.
- The right admin level varies by country. Uganda's ADM1 is only 4 regions, so Kampala
  is ADM2. Lima uses the metropolitan municipality, not the Lima region.

`make-sample` fails if any crosswalk `gb_shape_id` is missing upstream, which would mean
geoBoundaries re-issued its IDs.

## Data quality findings so far

| Finding | Where | Handling |
|---|---|---|
| 775 names mis-encoded (UTF-8 read as Latin-1), e.g. `SÃ£o Paulo`, `MÃ©xico` | EDGAR source file | Kept as-is in raw; repaired in `stg_edgar__urban_centres` (cp1252 mojibake, 775 rows); 339 names lost characters to `?` upstream and cannot be repaired (none are crosswalk cities, tested) |
| 192 duplicate (name, country) pairs | EDGAR | Join on IDs via the crosswalk |
| No negative or blank values across 11,686 rows; GHG (CO2e) never below CO2 | EDGAR | dbt tests on `fct_urban_centre_emissions` (error severity) |
| Licence text truncated inside the file ("Unl…", "compli…") | EDGAR citations sheet | Licence recorded only as far as verified |
| Intermittent HTTP 504 | geoBoundaries (GitHub LFS) | Retries with backoff; per-file isolation |
| Urban centre ≠ administrative area | EDGAR vs geoBoundaries | Overlap share + flag in dbt (Stage 3, [ADR 0001](adr/0001-urban-centre-overlap.md)) |
| 264 EDGAR urban-centre IDs are not in GHS-UCDB V1.2 (mostly small centres in Yemen, Ethiopia, Iran, Sudan). EDGAR's IDs run 1–11,686 without gaps; V1.2 has 11,422 of them | EDGAR v2024 vs GHS-UCDB V1.2 | Reported by `id_match_edgar`. None are crosswalk cities. EDGAR was evidently built on an earlier UCDB release with 11,686 centres, so a matched ID's V1.2 polygon *may* differ from the one EDGAR used (see limitations) |
| 363 matched IDs have a different name in EDGAR and UCDB after repairing mojibake on both sides. In 320 of them the only difference is a character EDGAR lost to `?` (`O?Fallon` / `O’Fallon`); 43 are real naming differences, e.g. `San Jose` / `San Francisco` (same Bay Area centre), `New York` / `New York City`. One country differs (`Caspian Sea` / `Russia`, ID 143) | EDGAR vs GHS-UCDB | Naming conventions, not different places, in the cases checked. Another reason to join on ID. All 25 crosswalk cities agree (Delhi: `Ghaziabad [New Delhi]` / `New Delhi`) |
| 22 invalid polygons (ring self-intersection) | GHS-UCDB | Kept in raw; `ST_MakeValid` in dbt staging; none are crosswalk cities |
| geoBoundaries' *Accra Metropolis* is 5.7 km² (5.6 km² in the full-resolution file, so not a simplification artefact). The official area of today's Accra Metropolitan District is **20.4 km²** (Ghana Statistical Service, 2021 PHC General Report Vol. 3A, p. 80). Only 0.5% of the 1,121 km² urban centre lies inside the polygon | geoBoundaries GHA ADM2 (2019 districts, source "USAID Ghana HPNO, Ghana Statistical Service") | Checked 2026-11-07. The **unit is right**: Accra Metropolis *is* the Accra Metropolitan Assembly, which Ghana cut down to a small core when it created 9 new districts in 2018–19. The **polygon is not**: it is ~28% of the official area. Crosswalk unchanged; `review_status = needs_review`. Stage 3's 0.01 overlap test warns on it |
| geoBoundaries' *Ciudad Autónoma de Buenos Aires* is 948 km² and extends into the surrounding partidos. The official area is "slightly over 200 km²" (Buenos Aires city government); the crosswalk uses 200 km² | geoBoundaries ARG ADM1 (source "geoBoundaries, Wikimedia", year 2006) | Found while checking Accra. Same situation: right unit, wrong polygon. Crosswalk unchanged; `needs_review`. Its overlap share (0.40) looks plausible, so only an area check catches this. Stage 3 plan adds one |
