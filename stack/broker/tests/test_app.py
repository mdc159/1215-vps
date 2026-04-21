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


def _patch_cursor(monkeypatch, executed: dict[str, object], fetchone=None, fetchall=None):
    """Install a fake psycopg cursor that captures execute() args.

    Centralised because every checkpoint test needs exactly this shape;
    inlining it four times made the test file noisy.
    """

    class FakeCursor:
        def execute(self, query, params) -> None:
            executed["query"] = query
            executed["params"] = params

        def fetchone(self):
            return fetchone

        def fetchall(self):
            return fetchall or []

    @contextmanager
    def fake_db_cursor():
        yield FakeCursor()

    monkeypatch.setattr(broker_app_module, "db_cursor", fake_db_cursor)
    return FakeCursor


def test_upsert_checkpoint_is_idempotent(monkeypatch) -> None:
    """POST /checkpoints must use the 3-tuple primary key UPSERT
    so retrying ``broadcast_ack`` with the same cursor_value is a
    no-op and advancing it overwrites cursor_value + updated_at."""
    executed: dict[str, object] = {}
    _patch_cursor(
        monkeypatch,
        executed,
        fetchone={
            "provider_name": "hermes-ceo",
            "node_id": "linux-prototype",
            "checkpoint_kind": "replay-cursor",
            "cursor_value": "42",
            "source_event_id": "event-42",
            "updated_at": "2026-04-21T00:00:00Z",
            "metadata_json": {"note": "advanced by broadcast_ack"},
        },
    )

    client = TestClient(broker_app_module.app)
    response = client.post(
        "/checkpoints",
        json={
            "provider_name": "hermes-ceo",
            "node_id": "linux-prototype",
            "checkpoint_kind": "replay-cursor",
            "cursor_value": "42",
            "source_event_id": "event-42",
            "metadata_json": {"note": "advanced by broadcast_ack"},
        },
    )

    assert response.status_code == 200
    assert "ON CONFLICT (provider_name, node_id, checkpoint_kind) DO UPDATE" in executed["query"]
    cp = response.json()["checkpoint"]
    assert cp["cursor_value"] == "42"
    assert cp["checkpoint_kind"] == "replay-cursor"


def test_list_checkpoints_builds_filtered_query(monkeypatch) -> None:
    """GET /checkpoints with all three keys must produce the exact
    read-before-write query broadcast_ack needs."""
    executed: dict[str, object] = {}
    _patch_cursor(
        monkeypatch,
        executed,
        fetchall=[
            {
                "provider_name": "hermes-ceo",
                "node_id": "linux-prototype",
                "checkpoint_kind": "replay-cursor",
                "cursor_value": "42",
                "source_event_id": "event-42",
                "updated_at": "2026-04-21T00:00:00Z",
                "metadata_json": {},
            }
        ],
    )

    client = TestClient(broker_app_module.app)
    response = client.get(
        "/checkpoints",
        params={
            "provider_name": "hermes-ceo",
            "node_id": "linux-prototype",
            "checkpoint_kind": "replay-cursor",
        },
    )

    assert response.status_code == 200
    query = executed["query"]
    assert "provider_name = %s" in query
    assert "node_id = %s" in query
    assert "checkpoint_kind = %s" in query
    # Final param is the LIMIT, preceding three are the filters.
    assert executed["params"] == ("hermes-ceo", "linux-prototype", "replay-cursor", 100)
    assert response.json()["count"] == 1


def test_list_checkpoints_no_filters_still_works(monkeypatch) -> None:
    """No filters -> WHERE clause omitted; used for the board-health view."""
    executed: dict[str, object] = {}
    _patch_cursor(monkeypatch, executed, fetchall=[])

    client = TestClient(broker_app_module.app)
    response = client.get("/checkpoints")

    assert response.status_code == 200
    assert "WHERE" not in executed["query"]
    assert executed["params"] == (100,)


def test_list_events_filters_apply_conjunctively(monkeypatch) -> None:
    """The broadcast_read_feed skill depends on conjunctive filtering;
    event_type+run_id together must AND, not OR."""
    executed: dict[str, object] = {}
    _patch_cursor(monkeypatch, executed, fetchall=[])

    client = TestClient(broker_app_module.app)
    response = client.get(
        "/events",
        params={
            "event_type": "memory.published",
            "run_id": "r-123",
            "after_seq": 10,
            "limit": 25,
        },
    )

    assert response.status_code == 200
    query = executed["query"]
    assert "event_type = %s" in query
    assert "run_id = %s" in query
    assert "event_seq > %s" in query
    assert query.count(" AND ") == 2
    assert executed["params"] == ("memory.published", "r-123", 10, 25)


def test_list_events_rejects_below_minimum_after_seq() -> None:
    """after_seq must be non-negative; the broker explicitly guards
    against clients passing negative values as a form of "read all"."""
    client = TestClient(broker_app_module.app)
    response = client.get("/events", params={"after_seq": -1})
    assert response.status_code == 422
