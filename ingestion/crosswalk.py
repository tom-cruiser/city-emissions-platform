"""Read the city crosswalk seed: the single list of cities this platform covers.

The same CSV is a dbt seed (Stage 3). Ingestion only needs it to know which
geoBoundaries files to fetch, so the city list is never duplicated in code.
"""

import csv
from pathlib import Path

from ingestion.config import CROSSWALK_CSV


def read_crosswalk(path: Path = CROSSWALK_CSV) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def boundary_files_needed(path: Path = CROSSWALK_CSV) -> list[tuple[str, str]]:
    """Distinct (ISO3, ADM level) pairs, e.g. [('ARG', 'ADM1'), ...]: one geoBoundaries file each."""
    return sorted({(row["country_iso3"], row["gb_adm_level"]) for row in read_crosswalk(path)})
