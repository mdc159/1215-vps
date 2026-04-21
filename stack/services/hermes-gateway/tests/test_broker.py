"""Unit tests for hermes_gateway.broker.

Uses pytest-httpx's ``httpx_mock`` fixture so we never touch the real
broker at 127.0.0.1:8090. A separate integration test (Phase D
acceptance) exercises the live broker end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from pytest_httpx import HTTPXMock

from hermes_gateway.broker import (
    DEFAULT_BROKER_URL,
    BrokerClient,
    BrokerError,
)


@pytest.fixture
async def client() -> BrokerClient:
    c = BrokerClient()
    yield c
    await c.aclose()


def _node_payload(mock: HTTPXMock) -> dict:
    reqs = mock.get_requests(url=f"{DEFAULT_BROKER_URL}/nodes")
    assert len(reqs) == 1
    return reqs[0].json_body() if hasattr(reqs[0], "json_body") else _json(reqs[0])


def _json(req: httpx.Request) -> dict:
    import json as _j

    return _j.loads(req.content.decode())


async def test_ensure_node_posts_expected_payload(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    httpx_mock.add_response(
        url=f"{DEFAULT_BROKER_URL}/nodes", method="POST", json={"ok": True}
    )
    await client.ensure_node()
    posted = _json(httpx_mock.get_requests()[0])
    assert posted == {
        "node_id": "hermes-gateway",
        "node_role": "gateway",
        "display_name": "hermes-gateway (host)",
    }


async def test_ensure_session_posts_expected_payload(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    httpx_mock.add_response(
        url=f"{DEFAULT_BROKER_URL}/sessions", method="POST", json={"ok": True}
    )
    await client.ensure_session("sess-42")
    posted = _json(httpx_mock.get_requests()[0])
    assert posted == {
        "session_id": "sess-42",
        "node_id": "hermes-gateway",
        "surface": "hermes-gateway",
    }


async def test_publish_run_event_sets_idempotency_and_fields(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    httpx_mock.add_response(
        url=f"{DEFAULT_BROKER_URL}/events", method="POST", json={"ok": True}
    )
    fixed_ts = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)
    await client.publish_run_event(
        event_type="run.created",
        run_id="run-xyz",
        session_id="sess-42",
        payload={"profile": "orchestrator-ceo"},
        occurred_at=fixed_ts,
    )
    body = _json(httpx_mock.get_requests()[0])
    assert body["event_type"] == "run.created"
    assert body["run_id"] == "run-xyz"
    assert body["session_id"] == "sess-42"
    assert body["node_id"] == "hermes-gateway"
    assert body["payload_version"] == 1
    assert body["idempotency_key"] == "run-xyz:created"
    assert body["occurred_at"] == "2026-04-21T12:00:00Z"
    assert body["payload_json"] == {"profile": "orchestrator-ceo"}
    # event_id is a fresh UUID, not reused
    assert len(body["event_id"]) >= 32


async def test_idempotency_key_differs_per_event_type(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    # pytest-httpx consumes responses by default; register one per call.
    for _ in range(4):
        httpx_mock.add_response(
            url=f"{DEFAULT_BROKER_URL}/events", method="POST", json={"ok": True}
        )
    for event_type, expected in [
        ("run.created", "run-1:created"),
        ("run.started", "run-1:started"),
        ("run.completed", "run-1:completed"),
        ("run.failed", "run-1:failed"),
    ]:
        await client.publish_run_event(
            event_type=event_type,
            run_id="run-1",
            session_id="s",
        )
    keys = [_json(r)["idempotency_key"] for r in httpx_mock.get_requests()]
    assert keys == [
        "run-1:created",
        "run-1:started",
        "run-1:completed",
        "run-1:failed",
    ]


async def test_publish_run_event_rejects_empty_ids(client: BrokerClient) -> None:
    with pytest.raises(ValueError):
        await client.publish_run_event(
            event_type="run.created", run_id="", session_id="s"
        )
    with pytest.raises(ValueError):
        await client.publish_run_event(
            event_type="run.created", run_id="r", session_id=""
        )


async def test_broker_5xx_raises_brokererror(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    httpx_mock.add_response(
        url=f"{DEFAULT_BROKER_URL}/events", method="POST", status_code=500, text="boom"
    )
    with pytest.raises(BrokerError) as exc:
        await client.publish_run_event(
            event_type="run.failed", run_id="r", session_id="s"
        )
    assert "500" in str(exc.value)


async def test_broker_transport_error_raises_brokererror(
    httpx_mock: HTTPXMock, client: BrokerClient
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with pytest.raises(BrokerError):
        await client.ensure_node()
