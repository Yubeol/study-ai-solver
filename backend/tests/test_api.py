from fastapi.testclient import TestClient

from app.main import create_app


def test_health():
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_health_db(db_conn, settings):
    with TestClient(create_app()) as client:
        body = client.get("/health/db").json()
    assert body["status"] == "ok"
    assert body["schema"] and body["app_schema"]
    assert body["judge_provider"] == settings.judge_provider
