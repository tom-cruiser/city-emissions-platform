"""Liveness and readiness."""

from fastapi.testclient import TestClient

from api.main import create_app


def test_health_needs_no_database(make_settings):
    app = create_app(make_settings(db_port=1))  # nothing listens on port 1
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_ready_when_reporting_is_built(client):
    body = client.get("/ready").json()
    assert body["status"] == "ready" and body["current_versions"] > 0


def test_ready_is_503_when_the_database_is_down(make_settings):
    with TestClient(create_app(make_settings(db_port=1))) as c:
        r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["code"] == "database_unavailable"
