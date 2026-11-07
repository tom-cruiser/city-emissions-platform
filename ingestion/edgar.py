"""EDGAR 'Global emissions in urban areas' (v2024): read the workbook, load into raw."""

from pathlib import Path

import psycopg
from openpyxl import load_workbook
from psycopg.types.json import Jsonb

from ingestion.config import (
    EDGAR_DATA_SHEET,
    EDGAR_REQUIRED_COLUMNS,
    EDGAR_VARIABLES_SHEET,
)
from ingestion.versioning import FileVersion, LoadResult, register_version


class SourceFormatError(ValueError):
    """The file no longer looks like what this loader was written for."""


def read_edgar_workbook(path: Path) -> tuple[str, list[dict]]:
    """Return (unit, rows). Each row is {column header: cell value}, exactly as in the sheet.

    Fails loudly if the layout changed (missing sheet, unit or key columns): a silent
    partial load is worse than a failed run.
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = set(wb.sheetnames)
        for required in (EDGAR_DATA_SHEET, EDGAR_VARIABLES_SHEET):
            if required not in sheets:
                raise SourceFormatError(f"sheet {required!r} not found; sheets are {sorted(sheets)}")

        unit = None
        for label, value, *_ in wb[EDGAR_VARIABLES_SHEET].iter_rows(values_only=True):
            if label == "Units":
                unit = value
        if not unit:
            raise SourceFormatError(f"no 'Units' row in sheet {EDGAR_VARIABLES_SHEET!r}")

        rows = wb[EDGAR_DATA_SHEET].iter_rows(values_only=True)
        header = next(rows)
        missing = [c for c in EDGAR_REQUIRED_COLUMNS if c not in header]
        if missing:
            raise SourceFormatError(f"missing columns {missing}")

        records = [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
        return unit, records
    finally:
        wb.close()


def load_edgar(conn: psycopg.Connection, fv: FileVersion) -> LoadResult:
    """Load one EDGAR file into raw.edgar_ucdb_emissions. Does not commit."""
    unit, records = read_edgar_workbook(fv.file_path)
    version_id, created = register_version(conn, fv, row_count=len(records))
    if not created:
        return LoadResult(fv.source_name, fv.source_key, version_id, 0, skipped=True)

    # COPY streams all rows in one round trip: far faster than row-by-row INSERTs.
    with conn.cursor() as cur, cur.copy(
        "COPY raw.edgar_ucdb_emissions"
        " (dataset_version_id, source_row_number, source_unit, record) FROM STDIN"
    ) as copy:
        for row_number, record in enumerate(records, start=1):
            copy.write_row((version_id, row_number, unit, Jsonb(record)))

    return LoadResult(fv.source_name, fv.source_key, version_id, len(records), skipped=False)
