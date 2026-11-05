"""Download a file with retries, hashing it as it streams to disk."""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class DownloadedFile:
    path: Path
    sha256: str
    size_bytes: int
    downloaded_at: datetime


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    dest_dir: Path,
    filename: str,
    *,
    client: httpx.Client | None = None,
    attempts: int = 8,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadedFile:
    """Download `url` into `dest_dir` as `<sha256 prefix>_<filename>`.

    Naming files by content hash means a re-download of identical bytes lands on the
    same path, and a changed upstream file never overwrites the previous version.

    Retries timeouts, connection errors and 429/5xx with exponential backoff
    (geoBoundaries' GitHub/LFS hosting returns intermittent 504s). Other errors
    such as 404 fail immediately: retrying will not fix them.
    """
    client = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, read=300))
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_dir / f".{filename}.part"

    for attempt in range(1, attempts + 1):
        try:
            digest = hashlib.sha256()
            size = 0
            with client.stream("GET", url) as response:
                if response.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=response.request, response=response
                    )
                response.raise_for_status()
                with tmp_path.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
            break
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code in RETRYABLE_STATUS
            )
            if not retryable or attempt == attempts:
                tmp_path.unlink(missing_ok=True)
                raise
            sleep(min(2**attempt, 60))  # 2, 4, 8, 16, 32, 60, 60 s: ~3 min worst case

    sha256 = digest.hexdigest()
    final_path = dest_dir / f"{sha256[:12]}_{filename}"
    tmp_path.replace(final_path)
    return DownloadedFile(final_path, sha256, size, datetime.now(UTC))
