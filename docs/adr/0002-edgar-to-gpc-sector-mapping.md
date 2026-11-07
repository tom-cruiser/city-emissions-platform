# ADR 0002: EDGAR sectors to GPC sectors

- **Status:** Accepted as **provisional**. The whole mapping is **pending review by a city
  GHG inventory specialist**. Every row of `transform/seeds/edgar_sector_map.csv` has
  `review_status = needs_review` until that review is done.
- **Date:** 2026-11-07

## Context

City GHG reporting is organised by the **GPC** (Global Protocol for Community-Scale
Greenhouse Gas Inventories). It has five sectors: I Stationary energy, II Transportation,
III Waste, IV Industrial processes and product use (IPPU), and V Agriculture, forestry and
other land use (AFOLU). It also counts emissions by scope: 1 inside the boundary, 2 from
grid energy used inside it, 3 other emissions outside it caused by activity inside it.

EDGAR v2024 urban emissions come in six sectors named only in the file's
*List of variables* sheet: `Energy, Industry, Residential, Transport, Agriculture, Waste`.
The file does not say what each aggregate contains. The dataset page
(edgar.jrc.ec.europa.eu/dataset_ucdb) lists the pollutants and years but not sector
definitions. The method paper (Crippa et al. 2021, *ERL* 16 074033) could not be read
from this environment (its open copy is behind bot protection). **So the mapping below
is based on the sector names and EDGAR's usual conventions, not on a verified definition.**
That is the main reason it is provisional.

Users will want emissions labelled with GPC sectors, because that is what city
inventories use.

## Decision

1. **Map each EDGAR sector to the GPC sector(s) it most plausibly falls in**, in a seed
   (`edgar_sector_map.csv`), not in SQL. Changing the mapping means editing a reviewed CSV.

   | EDGAR | GPC | `mapping_quality` | Why not `direct` |
   |---|---|---|---|
   | Energy | I Stationary energy | approximate | Assumed to be energy industries (I.4). GPC reports grid-energy generation inside the boundary but **excludes it from the BASIC total** to avoid double counting with scope 2. EDGAR gives no way to separate it. |
   | Industry | I + IV | **mixed** | Assumed to combine fuel combustion in manufacturing (I.3) with process emissions (IV). One number, two GPC sectors: it cannot be split. |
   | Residential | I Stationary energy | approximate | Fuel combustion in buildings (I.1). Whether commercial/institutional buildings (I.2) are included is not verified. |
   | Transport | II Transportation | approximate | Whether aviation and waterborne navigation are included, and how they are allocated to urban centres, is not verified. |
   | Agriculture | V AFOLU | approximate | Agriculture only. AFOLU also covers land use and forestry, which this dataset does not provide. |
   | Waste | III Waste | approximate | GPC counts incineration with energy recovery under Stationary energy. EDGAR cannot separate it. |

2. **`mapping_quality`** says how far each EDGAR number can be read as a GPC sector number:
   - `direct`: inside one GPC sector, and the two definitions match. Nothing qualifies today.
   - `approximate`: inside one GPC sector, but the boundaries differ or are unverified.
     Fine for "roughly how big is transport", not for comparison with a city's own
     inventory line.
   - `mixed`: spans GPC sectors and cannot be split. Report it under its EDGAR name (e.g.
     "Industry (GPC I.3 + IV)"). Never assign it wholly to one GPC sector.

3. **EDGAR's sector names stay the primary label.** Every modelled row keeps
   `edgar_sector`. `gpc_sector_code`, `gpc_sector` and `mapping_quality` are added next to it,
   never in its place.

4. **We say "GPC-aligned sectors", never "GPC inventory".** These figures are not a GPC
   inventory and must not be presented as one:
   - **Scope 1 only.** EDGAR is spatially distributed direct emissions. There is no scope 2
     (grid electricity used in the city) and no scope 3. GPC BASIC requires scope 2 for
     stationary energy and transport.
   - **Wrong territory for GPC.** The figures are for the GHS urban centre, not the city's
     administrative boundary (ADR 0001, `city_territory_overlap`).
   - **Modelled top-down, not compiled from city activity data.** Gridded national
     estimates distributed with proxies, not a city's fuel sales, traffic counts or
     landfill records.
   - **Sector boundaries do not match** (decision 1). Industry is `mixed`; the others are
     unverified.
   - **No land use or forestry**, so AFOLU is incomplete.
   - **Eight non-consecutive years** (1975, 1990, 2000, 2005, 2010, 2015, 2020, 2022), not an
     annual inventory.

## Consequences

- Reporting and the API can group by GPC sector. They must show `mapping_quality`, and
  show `mixed` sectors under their EDGAR name.
- No GPC sector total is "complete". A GPC sector I total built from Energy + Residential
  leaves out the I.3 share hidden in Industry.
- The specialist review should (a) check each assumption above against Crippa et al. 2021
  and the EDGAR documentation, (b) set `mapping_quality` and `review_status` per row, and
  (c) decide whether Energy should be shown separately from the other stationary energy
  in line with the GPC BASIC rule. Accepting a row means changing the CSV; no code changes.

## Alternatives considered

- **Present EDGAR sectors only, without GPC labels.** Most honest, but users would map
  them to GPC in their heads, without the caveats. A documented mapping with a quality
  flag is better than an implicit one.
- **Split Industry between I.3 and IV with a fixed ratio.** Rejected: there is no
  city-level basis for a ratio, and it would invent precision.
