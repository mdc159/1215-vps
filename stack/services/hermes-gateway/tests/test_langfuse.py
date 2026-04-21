"""Unit tests for hermes_gateway.langfuse.

Verifies:
  * no-op behaviour when env is not configured
  * batch payload shape (``trace-create`` / ``observation-create``)
  * HTTP errors do not raise out of the client
  * ``trace_id`` is stable across calls (=run_id)
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from hermes_gateway.langfuse import LangfuseClient


@pytest.mark.asyncio
async def test_no_op_when_env_missing() -> None:
    """Without LANGFUSE_HOST/KEYS the client must silently no-op so
    bare-stack prototypes without Langfuse still work."""
    client = LangfuseClient(host=None, public_key=None, secret_key=None)
    async with client:
        # Neither call should raise or try to make an HTTP request.
        await client.create_trace(
            run_id="r-1", session_id="s-1", profile="orchestrator-ceo", prompt="hi"
        )
        await client.create_span(trace_id="r-1", name="run.created")


@pytest.mark.asyncio
async def test_create_trace_posts_batch_with_trace_id(monkeypatch) -> None:
    """trace-create must use run_id as the top-level Langfuse id."""
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/public/ingestion"
        body = request.read()
        import json as _json

        captured.append(_json.loads(body))
        return httpx.Response(207, json={"successes": [], "errors": []})

    transport = httpx.MockTransport(handler)

    client = LangfuseClient(
        host="http://langfuse.test",
        public_key="pk",
        secret_key="sk",
    )
    # Use the mock transport for an isolated test; we still want to
    # exercise the real auth + JSON-serialisation path.
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        auth=("pk", "sk"), transport=transport
    )

    await client.create_trace(
        run_id="run-abc",
        session_id="sess-xyz",
        profile="orchestrator-ceo",
        prompt="say hi",
        metadata={"model": "openai/gpt-4o-mini"},
    )
    await client.create_span(
        trace_id="run-abc",
        name="run.started",
        metadata={"pid": 4321},
    )
    await client.aclose()

    assert len(captured) == 2
    trace_batch = captured[0]
    assert trace_batch["batch"][0]["type"] == "trace-create"
    assert trace_batch["batch"][0]["body"]["id"] == "run-abc"
    assert trace_batch["batch"][0]["body"]["sessionId"] == "sess-xyz"
    assert trace_batch["batch"][0]["body"]["metadata"]["profile"] == "orchestrator-ceo"
    assert trace_batch["batch"][0]["body"]["metadata"]["model"] == "openai/gpt-4o-mini"

    span_batch = captured[1]
    assert span_batch["batch"][0]["type"] == "observation-create"
    assert span_batch["batch"][0]["body"]["traceId"] == "run-abc"
    assert span_batch["batch"][0]["body"]["type"] == "SPAN"
    assert span_batch["batch"][0]["body"]["name"] == "run.started"


@pytest.mark.asyncio
async def test_network_error_is_swallowed() -> None:
    """Langfuse being unreachable must never fail a run; the client
    should log + continue so broker continuity is unaffected."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)

    client = LangfuseClient(
        host="http://langfuse.test",
        public_key="pk",
        secret_key="sk",
    )
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        auth=("pk", "sk"), transport=transport
    )

    await client.create_trace(
        run_id="r-err", session_id="s-err", profile="orchestrator-ceo", prompt="p"
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_span_level_error_for_failed_run(monkeypatch) -> None:
    """A run.failed span must carry level=ERROR so Langfuse dashboards
    can colour-code failed runs distinctly from successful ones."""
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.append(_json.loads(request.read()))
        return httpx.Response(207, json={})

    transport = httpx.MockTransport(handler)

    client = LangfuseClient(
        host="http://langfuse.test", public_key="pk", secret_key="sk"
    )
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        auth=("pk", "sk"), transport=transport
    )

    await client.create_span(
        trace_id="run-err",
        name="run.failed",
        level="ERROR",
        status_message="returncode=2",
    )
    await client.aclose()

    span = captured[0]["batch"][0]["body"]
    assert span["level"] == "ERROR"
    assert span["statusMessage"] == "returncode=2"
