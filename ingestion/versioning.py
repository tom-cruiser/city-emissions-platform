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
    origin: str  # 'download' or 'sample'
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


def repo_relative(path: Path) -> str:
    """Store paths relative to the repo so they mean the same on the host and in containers."""
    path = path.resolve()
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def register_version(conn: psycopg.Connection, fv: FileVersion, row_count: int) -> int | None:
    """Insert the dataset version. Returns its id, or None if this file is already loaded.

    ON CONFLICT DO NOTHING on (source_name, source_key, file_sha256) makes re-runs no-ops
    and is safe if two loads race: the second waits on the unique index, then does nothing.
    """
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
    return row[0] if row else None
