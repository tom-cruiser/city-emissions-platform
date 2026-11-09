"""Static checks on how the services are deployed. The API gets only the reader's
credentials; Dagster only the pipeline's and its own storage role's. Both are reachable only
from localhost, and each image installs only its own dependency groups."""

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


# --- Dagster (webserver + daemon) ---

DAGSTER = {name: COMPOSE["services"][name] for name in ("dagster-webserver", "dagster-daemon")}
DAGSTER_ENV = {"PGHOST", "POSTGRES_PORT", "POSTGRES_DB", "PIPELINE_USER", "PIPELINE_PASSWORD",
               "PIPELINE_TARGET", "DAGSTER_PG_DB", "DAGSTER_PG_USER", "DAGSTER_PG_PASSWORD"}


def test_dagster_gets_only_pipeline_and_storage_credentials():
    for name, service in DAGSTER.items():
        env = service["environment"]
        assert set(env) == DAGSTER_ENV, name  # no API reader, test role or superuser
        assert env["PIPELINE_TARGET"] == "warehouse"
        assert env["PIPELINE_USER"] == "${PIPELINE_USER}" and env["DAGSTER_PG_USER"] == "${DAGSTER_PG_USER}"


def test_dagster_ui_is_local_only_and_the_daemon_has_no_ports():
    assert DAGSTER["dagster-webserver"]["ports"] == ["127.0.0.1:${DAGSTER_PORT:-3030}:3000"]
    assert "ports" not in DAGSTER["dagster-daemon"]
    assert DAGSTER["dagster-daemon"]["command"][:2] == ["dagster-daemon", "run"]


def test_dagster_services_are_hardened():
    for name, service in DAGSTER.items():
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name
        assert service["depends_on"]["db"]["condition"] == "service_healthy", name
        assert service["build"]["dockerfile"] == "orchestration/Dockerfile", name


def test_dagster_image_installs_pipeline_and_orchestration_only():
    dockerfile = (REPO_ROOT / "orchestration" / "Dockerfile").read_text()
    assert "uv sync --frozen --no-default-groups --group pipeline --group orchestration --no-install-project" \
        in dockerfile
    assert "--group api" not in dockerfile
    assert "USER dagster" in dockerfile and "ARG GIT_COMMIT" in dockerfile


def test_dagster_build_context_is_an_allowlist():
    lines = [line for line in (REPO_ROOT / "orchestration" / "Dockerfile.dockerignore").read_text().splitlines()
             if line and not line.startswith("#")]
    assert lines[0] == "*"
    included = {line[1:] for line in lines if line.startswith("!")}
    assert included == {"pyproject.toml", "uv.lock", "ingestion/", "transform/", "orchestration/",
                        "scripts/git-commit.sh"}


def test_dagster_storage_is_its_own_database():
    db_env = COMPOSE["services"]["db"]["environment"]
    assert {"DAGSTER_PG_DB", "DAGSTER_PG_USER", "DAGSTER_PG_PASSWORD"} <= set(db_env)
    storage = yaml.safe_load((REPO_ROOT / "orchestration" / "dagster.yaml").read_text())["storage"]["postgres"]
    pg = storage["postgres_db"]
    assert pg["db_name"] == {"env": "DAGSTER_PG_DB"} and pg["username"] == {"env": "DAGSTER_PG_USER"}
    assert pg["scheme"] == "postgresql+psycopg2"
