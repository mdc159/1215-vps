from __future__ import annotations

from fastapi.testclient import TestClient

from broker_service import app as broker_app_module


def test_show_config(monkeypatch) -> None:
    monkeypatch.setenv("BROKER_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("BROKER_SERVICE_NAME", "test-broker")

    client = TestClient(broker_app_module.app)
    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == {
        "database_url": "postgresql://example",
        "service_name": "test-broker",
    }
