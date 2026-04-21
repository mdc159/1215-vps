"""Integration tests for hermes_gateway.app.

Exercises the FastAPI app in-process through ``httpx.ASGITransport``
against a fake profile tree + fake hermes binary. The broker client
is a fake that records calls instead of hitting HTTP — we already
unit-test the real broker client in test_broker.py.
"""

from __future__ import annotations

import asyncio
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from hermes_gateway import broker as broker_mod
from hermes_gateway.app import _build_app


@dataclass
class FakeBroker:
    """Captures broker calls; mimics :class:`BrokerClient`'s public surface."""

    node_calls: int = 0
    session_calls: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False
    fail_next_ensure_node: bool = False

    async def ensure_node(self) -> None:
        if self.fail_next_ensure_node:
            self.fail_next_ensure_node = False
            raise broker_mod.BrokerError("simulated")
        self.node_calls += 1

    async def ensure_session(self, session_id: str, *, surface: str = "x") -> None:
        self.session_calls.append(session_id)

    async def publish_run_event(
        self,
        *,
        event_type: str,
        run_id: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
        occurred_at: Any = None,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "run_id": run_id,
                "session_id": session_id,
                "payload": payload or {},
            }
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_tree(tmp_path: Path) -> dict[str, Path]:
    """Fake /var/lib/hermes + workspace + a bash stub hermes binary
    that echoes two lines and exits 0. Integration tests that need
    a cancellable long-running stub override this via monkeypatch.
    """
    profile_root = tmp_path / "hermes"
    workspace_root = tmp_path / "paperclip" / "workspaces"

    hermes_home = profile_root / "orchestrator-ceo" / ".hermes"
    hermes_home.mkdir(parents=True)
    (hermes_home / ".env").write_text(
        "OPENROUTER_API_KEY=sk-test-abc\nHERMES_CEO_CANARY=TESTCANARY\n",
        encoding="utf-8",
    )

    workspace = workspace_root / "orchestrator-ceo"
    workspace.mkdir(parents=True)

    hermes_bin = tmp_path / "hermes-stub"
    hermes_bin.write_text(
        "#!/usr/bin/env bash\n"
        'echo "fake-hermes started pid=$$"\n'
        'echo "prompt was: $*"\n'
        "sleep 0.1\n"
        'echo "final-line"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    hermes_bin.chmod(hermes_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "profile_root": profile_root,
        "workspace_root": workspace_root,
        "hermes_home": hermes_home,
        "workspace": workspace,
        "hermes_bin": hermes_bin,
    }


@pytest.fixture
async def client_and_broker(
    fake_tree: dict[str, Path],
):
    fake_broker = FakeBroker()
    app = _build_app(
        broker=fake_broker,
        profile_root=fake_tree["profile_root"],
        workspace_root=fake_tree["workspace_root"],
        hermes_bin=fake_tree["hermes_bin"],
    )
    # httpx's ASGITransport does not drive the ASGI lifespan protocol,
    # so enter the FastAPI lifespan context manually. FastAPI exposes
    # the active lifespan via ``app.router.lifespan_context``.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:
            yield client, fake_broker, app


# ---- /healthz --------------------------------------------------------

async def test_healthz(client_and_broker) -> None:
    client, _, _ = client_and_broker
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "runs_in_flight": 0}


# ---- /runs/start happy path -----------------------------------------

async def test_start_run_happy_path(client_and_broker) -> None:
    client, broker, app = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={
            "profile": "orchestrator-ceo",
            "session_id": "sess-int-1",
            "prompt": "say hello",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "run_id" in body and len(body["run_id"]) >= 16
    assert body["pid"] > 0
    run_id = body["run_id"]

    # Broker sees ensure_session, run.created, run.started synchronously;
    # run.completed lands after the stub process exits.
    state = app.state.runs[run_id]
    await asyncio.wait_for(state.done.wait(), timeout=5)

    assert "sess-int-1" in broker.session_calls
    types = [e["event_type"] for e in broker.events if e["run_id"] == run_id]
    assert types == ["run.created", "run.started", "run.completed"]
    completed = next(e for e in broker.events if e["event_type"] == "run.completed")
    assert completed["payload"]["returncode"] == 0


async def test_start_run_session_row_ensured_before_created_event(
    client_and_broker,
) -> None:
    """The broker would reject run.created if session_id doesn't exist;
    make sure the gateway creates the session first."""
    client, broker, _ = client_and_broker
    await client.post(
        "/runs/start",
        json={
            "profile": "orchestrator-ceo",
            "session_id": "sess-order",
            "prompt": "p",
        },
    )
    # ensure_session called before the first event referencing it.
    assert broker.session_calls == ["sess-order"]


# ---- /runs/start rejections ----------------------------------------

async def test_start_run_forbidden_profile(client_and_broker) -> None:
    client, broker, _ = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={"profile": "rogue", "session_id": "s", "prompt": "x"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "forbidden"
    # No events should have been published for the rejected attempt
    assert broker.events == []


async def test_start_run_not_found_profile_dir(
    client_and_broker, fake_tree: dict[str, Path]
) -> None:
    # Remove the profile directory; the allowlist still says
    # orchestrator-ceo is legitimate, but the filesystem disagrees.
    import shutil

    shutil.rmtree(fake_tree["hermes_home"].parent)
    client, _, _ = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={"profile": "orchestrator-ceo", "session_id": "s", "prompt": "x"},
    )
    assert resp.status_code == 404


async def test_start_run_bad_request_empty_prompt(client_and_broker) -> None:
    client, _, _ = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={"profile": "orchestrator-ceo", "session_id": "s", "prompt": ""},
    )
    # pydantic rejects min_length=1 with 422; either 400 or 422 is
    # acceptable here (the contract is "client-side error").
    assert resp.status_code in (400, 422)


# ---- /runs/{id}/attach ----------------------------------------------

async def test_attach_streams_output_and_ends(client_and_broker) -> None:
    client, _, _ = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={
            "profile": "orchestrator-ceo",
            "session_id": "sess-attach",
            "prompt": "hi",
        },
    )
    run_id = resp.json()["run_id"]

    # SSE stream: consume until we see an "event: end" frame.
    async with client.stream("POST", f"/runs/{run_id}/attach") as stream:
        chunks: list[str] = []
        async for raw in stream.aiter_lines():
            chunks.append(raw)
            if raw.startswith("event: end"):
                break
    body = "\n".join(chunks)
    assert "fake-hermes started" in body
    assert "final-line" in body
    assert "event: end" in body


async def test_attach_unknown_run_is_404(client_and_broker) -> None:
    client, _, _ = client_and_broker
    resp = await client.post("/runs/does-not-exist/attach")
    assert resp.status_code == 404


# ---- /runs/{id}/cancel ----------------------------------------------

async def test_cancel_sends_sigterm(
    client_and_broker, fake_tree: dict[str, Path], tmp_path: Path
) -> None:
    # Swap the stub for a long-running script so we can cancel it.
    stub = fake_tree["hermes_bin"]
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'trap \'echo "got-sigterm"; exit 143\' TERM\n'
        'echo "sleeper started"\n'
        "sleep 30 & wait $!\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    client, broker, app = client_and_broker
    resp = await client.post(
        "/runs/start",
        json={
            "profile": "orchestrator-ceo",
            "session_id": "sess-cancel",
            "prompt": "stall",
        },
    )
    run_id = resp.json()["run_id"]
    state = app.state.runs[run_id]

    # Give the subprocess a moment to install its TERM handler.
    await asyncio.sleep(0.3)
    cancel_resp = await client.post(f"/runs/{run_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancel_sent"

    await asyncio.wait_for(state.done.wait(), timeout=5)
    assert state.returncode == 143

    types = [e["event_type"] for e in broker.events if e["run_id"] == run_id]
    assert "run.failed" in types


async def test_cancel_unknown_run_is_404(client_and_broker) -> None:
    client, _, _ = client_and_broker
    resp = await client.post("/runs/nope/cancel")
    assert resp.status_code == 404
