"""Static checks on how the API is deployed: it gets only the reader's credentials, is
reachable only from localhost, and its image installs only the `api` dependency group."""

import yaml

from ingestion.config import REPO_ROOT

COMPOSE = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
API = COMPOSE["services"]["api"]


def test_api_container_gets_only_the_reader_credentials():
    assert set(API["environment"]) == {"PGHOST", "POSTGRES_PORT", "POSTGRES_DB",
                                       "API_READER_USER", "API_READER_PASSWORD"}
    assert API["environment"]["API_READER_USER"] == "${API_READER_USER}"


def test_api_container_is_hardened_and_local_only():
    assert all(p.startswith("127.0.0.1:") for p in API["ports"])
    assert API["read_only"] is True and API["cap_drop"] == ["ALL"]
    assert API["depends_on"]["db"]["condition"] == "service_healthy"


def test_api_image_installs_only_the_api_group():
    dockerfile = (REPO_ROOT / "api" / "Dockerfile").read_text()
    assert "uv sync --frozen --no-default-groups --group api" in dockerfile
    assert "USER api" in dockerfile


def test_build_context_excludes_secrets():
    ignored = (REPO_ROOT / ".dockerignore").read_text().split()
    assert ".env" in ignored and "data/" in ignored and "backups/" in ignored
