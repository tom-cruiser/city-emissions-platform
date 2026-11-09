# Data sources and licences

Sources, licences, citations, and sources not used. Back to the [README](../README.md).

## Data sources & licences

| Source | Used for | Licence | Committed to this repo? |
|---|---|---|---|
| **EDGAR – Global emissions in urban areas, v2024** (European Commission, JRC) [dataset page](https://edgar.jrc.ec.europa.eu/dataset_ucdb) | GHG per urban centre and sector, 1975–2022, t CO2e (GWP100, AR5) | © European Union 2024, JRC. The IEA-EDGAR CO2 component (fossil fuel combustion) is **CC BY-NC-ND 4.0**. The general licence text is truncated in the file and not stated on the [terms page](https://edgar.jrc.ec.europa.eu/terms). | **No real rows.** Downloaded at run time. The repo holds only a [synthetic fixture](ingestion.md#synthetic-edgar-fixture) with EDGAR's structure and invented values. |
| **geoBoundaries gbOpen** (William & Mary geoLab) [geoboundaries.org](https://www.geoboundaries.org) | Administrative boundaries, ADM1/ADM2 | Per country, see below | Yes: one polygon per city, unmodified, in `data/sample/geoboundaries/` |
| **GHS Urban Centre Database R2024A, V1-2** (European Commission, JRC, GHSL) [product page](https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php) | Urban-centre polygons; urban-centre IDs and names in the synthetic fixture | **CC BY 4.0**, per the V1-2 [`copyright.txt`](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_UCDB_GLOBE_R2024A/GHS_UCDB_GLOBE_R2024A/V1-2/copyright.txt) (re-checked 2026-11-06): reuse allowed with credit and with changes indicated | Yes: the 25 crosswalk urban centres, one layer, attributes and geometry unchanged (160 KB). The changes are listed in `manifest.json` |

EDGAR citation (from the dataset page): Crippa, M. et al., *EDGAR_emissions_urban_areas*,
European Commission, Joint Research Centre (JRC), http://data.europa.eu/89h/c0c49cd7-4a80-4a94-8c34-375289c12b2d.
See also Crippa et al. (2021), *Environmental Research Letters* 16, 074033,
doi:10.1088/1748-9326/ac00e2.

GHS-UCDB citation (from the dataset readme): Mari Rivero, I.; Melchiorri, M.; Florio, P.;
Schiavina, M. et al. (2024): *GHS-UCDB R2024A - GHS Urban Centre Database 2025*. European
Commission, Joint Research Centre (JRC). doi:10.2905/1a338be6-7eaf-480c-9664-3a8ade88cbcd

geoBoundaries citation: Runfola, D. et al. (2020), *geoBoundaries: A global database of
political administrative boundaries*, PLoS ONE 15(4): e0231866.

**geoBoundaries licences per file** (as reported by the geoBoundaries API; each file is
fetched from a commit-pinned GitHub URL, recorded in `raw.dataset_versions.source_url`):

| Licence | Countries |
|---|---|
| CC BY 4.0 | ETH, GHA, NGA, RWA |
| CC BY 3.0 IGO | BRA, MEX, SEN, ZAF |
| CC BY 2.5 (Generic / India) | ARG, IND |
| ODbL 1.0 (share-alike for databases) | COD, COL, EGY, IDN, JPN, THA, TZA |
| Data licence Germany – Attribution 2.0 | DEU |
| Etalab Open Licence 2.0 | FRA |
| Public domain / CC0 | BDI, KEN, KOR, PER, UGA |

**Sources evaluated and not used**

- **CDP open data** (data.cdp.net) returns HTTP 403 to automated clients. A scheduled
  pipeline cannot depend on it, and its bot protection was not circumvented.
- **Climate TRACE**: the API is officially beta, and a city search for "Kigali" returned
  no results. Its city data is offered via manual downloads on the Explore page.
