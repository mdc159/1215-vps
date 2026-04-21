from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from broker_service import app as broker_app_module


def test_show_config(monkeypatch) -> None:
    monkeypatch.setenv("BROKER_DATABASE_HOST", "postgres")
    monkeypatch.setenv("BROKER_DATABASE_NAME", "postgres")
    monkeypatch.setenv("BROKER_DATABASE_USER", "postgres")
    monkeypatch.setenv("BROKER_DATABASE_PASSWORD", "secret")
    monkeypatch.setenv("BROKER_SERVICE_NAME", "test-broker")

    client = TestClient(broker_app_module.app)
    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == {
        "database_source": "parts",
        "database_host": "postgres",
        "database_name": "postgres",
        "database_user": "postgres",
        "service_name": "test-broker",
    }


def test_create_session_is_idempotent(monkeypatch) -> None:
    executed: dict[str, object] = {}

    class FakeCursor:
        def execute(self, query, params) -> None:
            executed["query"] = query
            executed["params"] = params

        def fetchone(self):
            return {
                "session_id": "sess-123",
                "node_id": "node-123",
                "surface": "openwebui",
                "metadata_json": {"user_id": "user-123"},
                "created_at": "2026-04-20T00:00:00Z",
            }

    @contextmanager
    def fake_db_cursor():
        yield FakeCursor()

    monkeypatch.setattr(broker_app_module, "db_cursor", fake_db_cursor)

    client = TestClient(broker_app_module.app)
    response = client.post(
        "/sessions",
        json={
            "session_id": "sess-123",
            "node_id": "node-123",
            "surface": "openwebui",
            "metadata_json": {"user_id": "user-123"},
        },
    )

    assert response.status_code == 200
    assert "ON CONFLICT (session_id) DO UPDATE" in executed["query"]
    assert response.json()["session"]["session_id"] == "sess-123"


def test_create_artifact_is_idempotent(monkeypatch) -> None:
    executed: dict[str, object] = {}

    class FakeCursor:
        def execute(self, query, params) -> None:
            executed["query"] = query
            executed["params"] = params

        def fetchone(self):
            return {
                "artifact_id": "artifact-123",
                "artifact_kind": "blob",
                "source_event_id": "event-123",
                "source_event_hash": "hash-123",
                "storage_backend": "s3",
                "uri": "s3://artifacts/prototype/foo.png",
                "mime_type": "image/png",
                "checksum_sha256": "abc123",
                "metadata_json": {"bucket": "artifacts", "object_key": "prototype/foo.png"},
                "created_at": "2026-04-21T00:00:00Z",
            }

    @contextmanager
    def fake_db_cursor():
        yield FakeCursor()

    monkeypatch.setattr(broker_app_module, "db_cursor", fake_db_cursor)

    client = TestClient(broker_app_module.app)
    response = client.post(
        "/artifacts",
        json={
            "artifact_id": "artifact-123",
            "artifact_kind": "blob",
            "source_event_id": "event-123",
            "source_event_hash": "hash-123",
            "storage_backend": "s3",
            "uri": "s3://artifacts/prototype/foo.png",
            "mime_type": "image/png",
            "checksum_sha256": "abc123",
            "metadata_json": {"bucket": "artifacts", "object_key": "prototype/foo.png"},
        },
    )

    assert response.status_code == 200
    assert "ON CONFLICT (storage_backend, uri) DO UPDATE" in executed["query"]
    assert response.json()["artifact"]["uri"] == "s3://artifacts/prototype/foo.png"
