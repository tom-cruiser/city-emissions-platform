import hashlib

import httpx
import pytest

from ingestion.download import download, sha256_file

BODY = b'{"type": "FeatureCollection", "features": []}'


def client_returning(*statuses: int) -> tuple[httpx.Client, list[int]]:
    """A fake HTTP client that answers with the given status codes in order."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses[len(calls)]
        calls.append(status)
        return httpx.Response(status, content=BODY if status == 200 else b"error")

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_sha256_file_matches_known_digest(tmp_path):
    f = tmp_path / "abc.txt"
    f.write_bytes(b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_retries_gateway_timeouts_then_succeeds(tmp_path):
    client, calls = client_returning(504, 504, 200)
    result = download("https://example.test/f.geojson", tmp_path, "f.geojson",
                      client=client, sleep=lambda s: None)

    assert calls == [504, 504, 200]
    assert result.sha256 == hashlib.sha256(BODY).hexdigest()
    assert result.path.name == f"{result.sha256[:12]}_f.geojson"  # content-addressed name
    assert result.path.read_bytes() == BODY
    assert not list(tmp_path.glob(".*.part"))  # no temp file left behind


def test_does_not_retry_not_found(tmp_path):
    client, calls = client_returning(404, 200)
    with pytest.raises(httpx.HTTPStatusError):
        download("https://example.test/missing", tmp_path, "f", client=client, sleep=lambda s: None)
    assert calls == [404]


def test_gives_up_after_max_attempts(tmp_path):
    client, calls = client_returning(503, 503, 503)
    with pytest.raises(httpx.HTTPStatusError):
        download("https://example.test/f", tmp_path, "f", client=client,
                 attempts=3, sleep=lambda s: None)
    assert len(calls) == 3
