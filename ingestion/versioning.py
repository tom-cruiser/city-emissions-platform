"""Dataset versions: the lineage record for every file loaded into raw."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg

from ingestion.config import REPO_ROOT


@dataclass(frozen=True)
class FileVersion:
    """Everything we know about one source file before loading it."""

    source_name: str
    source_key: str
    origin: str  # 'download', 'sample' or 'synthetic'
    source_url: str
    file_path: Path
    sha256: str
    size_bytes: int
    downloaded_at: datetime
    license: str | None = None
    upstream_sha256: str | None = None


@dataclass(frozen=True)
class LoadResult:
    source_name: str
    source_key: str
    dataset_version_id: int | None
    rows_loaded: int
    skipped: bool  # True when this exact file was already loaded
    error: str | None = None  # set when this file failed; other files still load
    warnings: tuple[str, ...] = ()  # load checks that passed with a warning (raw.load_checks)


class NotATestDatabaseError(RuntimeError):
    """Raised when sample or synthetic data would be loaded outside a *_test database."""


def require_test_database(conn: psycopg.Connection, what: str) -> None:
    """Refuse to continue unless `conn` is connected to a database whose name ends in "_test".

    Sample and synthetic data must never reach the real warehouse: the synthetic EDGAR
    fixture holds invented emissions. The check uses the database the connection actually
    reached, not a configured name, and accepts only the "_test" naming convention that
    tests already rely on (tests/conftest.py), so a renamed warehouse is refused too.
    """
    dbname = conn.info.dbname
    if not dbname.endswith("_test"):
        raise NotATestDatabaseError(
            f"refusing to load {what} into database {dbname!r}: sample and synthetic data may only be "
            "loaded into a *_test database (use --target test)"
        )


def repo_relative(path: Path) -> str:
    """Store paths relative to the repo so they mean the same on the host and in containers."""
    path = path.resolve()
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def register_version(conn: psycopg.Connection, fv: FileVersion, row_count: int) -> tuple[int, bool]:
    """Insert the dataset version. Returns (dataset_version_id, created).

    created is False when this exact file is already loaded; the id is then the existing
    version's, so a skipped re-run can still say which version it matched.
    ON CONFLICT DO NOTHING on (source_name, source_key, file_sha256) makes re-runs no-ops
    and is safe if two loads race: the second waits on the unique index, then does nothing.
    Every loader registers through here, so this is also where non-download data is
    stopped from reaching a real database.
    """
    if fv.origin != "download":
        require_test_database(conn, f"{fv.origin} data ({fv.source_name} {fv.source_key})")
    row = conn.execute(
        """
        INSERT INTO raw.dataset_versions
            (source_name, source_key, origin, source_url, file_path, file_sha256,
             file_size_bytes, upstream_sha256, license, downloaded_at, row_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_name, source_key, file_sha256) DO NOTHING
        RETURNING dataset_version_id
        """,
        (
            fv.source_name,
            fv.source_key,
            fv.origin,
            fv.source_url,
            repo_relative(fv.file_path),
            fv.sha256,
            fv.size_bytes,
            fv.upstream_sha256,
            fv.license,
            fv.downloaded_at,
            row_count,
        ),
    ).fetchone()
    if row:
        return row[0], True
    existing = conn.execute(
        "SELECT dataset_version_id FROM raw.dataset_versions"
        " WHERE source_name = %s AND source_key = %s AND file_sha256 = %s",
        (fv.source_name, fv.source_key, fv.sha256),
    ).fetchone()
    return existing[0], False
