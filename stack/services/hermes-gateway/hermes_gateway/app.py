"""FastAPI app that owns the UNIX domain socket.

One process, one loop, one socket. The container never reaches this
directly over TCP; Paperclip bind-mounts the socket path at
``$XDG_RUNTIME_DIR/hermes-gateway/gateway.sock`` (host) to the same
path inside the container. All writes to the broker happen from this
process; the subprocesses Hermes spawns do not talk to the broker.

Endpoints
---------

``POST /runs/start``
    Body: ``{profile, session_id, prompt, model?}``. Returns 201 with
    ``{"run_id", "pid"}``. Rejects 403 for non-allowlisted profiles,
    400 for malformed input, 404 for missing profile/workspace files.

``POST /runs/{run_id}/attach``
    SSE stream of stdout (stderr merged) lines from the spawned run.
    Latecomers get replay from the beginning up to the live tail.

``POST /runs/{run_id}/cancel``
    SIGTERM the run's process group. 404 if the ``run_id`` is unknown.

``GET /healthz``
    ``{"ok": true}``. Used by the systemd unit health probe.

Lifecycle
---------

On StartRun the app:

  1. Calls :func:`spawn.build_spawn_plan` synchronously. Any policy
     failure becomes the HTTP error before any subprocess exists.
  2. Calls ``broker.ensure_session`` so downstream consumers can key
     off ``session_id`` without racing the first event.
  3. Publishes ``run.created`` (best-effort: broker failure logs but
     does NOT abort the run; continuity is durable, not the path).
  4. ``asyncio.create_subprocess_exec(*plan.argv, env=plan.env,
     cwd=plan.cwd, ...)`` with ``start_new_session=True`` so we can
     SIGTERM the full pgrp on cancel.
  5. Publishes ``run.started`` with the pid.
  6. Schedules a background task that drains stdout into a per-run
     :class:`RunState` buffer (and fan-out queues for attachers),
     then publishes ``run.completed`` (rc == 0) or ``run.failed``
     (rc != 0) with the rc in ``payload_json``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import broker as broker_mod
from . import langfuse as langfuse_mod
from . import spawn as spawn_mod

_log = logging.getLogger("hermes_gateway.app")

# Sentinel for "subprocess has exited; downstream consumers should finish"
_EOF = object()


class StartRunRequest(BaseModel):
    profile: str = Field(..., min_length=1, max_length=64)
    session_id: str = Field(..., min_length=1, max_length=128)
    prompt: str = Field(..., min_length=1, max_length=32_000)
    model: str | None = Field(default=None, max_length=128)


class StartRunResponse(BaseModel):
    run_id: str
    pid: int


@dataclass
class RunState:
    """Per-run in-memory state.

    The gateway is deliberately non-durable: broker events are the
    source of truth for continuity, and RunState only lives long
    enough to serve attach/cancel. Crash-restart wipes every in-flight
    run, which is acceptable for the prototype scope (Phase D's job
    is isolation, not HA).
    """

    run_id: str
    session_id: str
    profile: str
    process: asyncio.subprocess.Process
    plan: spawn_mod.SpawnPlan
    output: list[bytes] = field(default_factory=list)
    subscribers: list[asyncio.Queue[bytes | object]] = field(default_factory=list)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    returncode: int | None = None


def _build_app(
    *,
    broker: broker_mod.BrokerClient | None = None,
    langfuse: langfuse_mod.LangfuseClient | None = None,
    profile_root: Path | None = None,
    workspace_root: Path | None = None,
    hermes_bin: Path | None = None,
) -> FastAPI:
    """Construct the FastAPI app.

    Parameters are injectable so integration tests can point at a
    throwaway profile tree without stubbing module-level constants.
    """

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        # Register the gateway node once per process. Failure here is
        # logged but not fatal — Paperclip can still drive runs, and
        # the session-ensure path retries node registration implicitly.
        try:
            await fastapi_app.state.broker.ensure_node()
        except broker_mod.BrokerError as exc:  # pragma: no cover - infra
            _log.warning("broker.ensure_node failed at startup: %s", exc)
        # Open the Langfuse httpx client once; if Langfuse env is not
        # set the context manager installs a no-op client.
        await fastapi_app.state.langfuse.__aenter__()
        try:
            yield
        finally:
            # SIGTERM any in-flight process groups so shutdown doesn't
            # leak orphans; then close the broker and Langfuse clients.
            for state in list(fastapi_app.state.runs.values()):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(state.process.pid, signal.SIGTERM)
            await fastapi_app.state.broker.aclose()
            await fastapi_app.state.langfuse.aclose()

    app = FastAPI(
        title="hermes-gateway",
        version="0.1.0",
        description=(
            "Host-side UDS daemon that spawns Hermes runs on behalf "
            "of the Paperclip container."
        ),
        lifespan=lifespan,
    )

    app.state.runs: dict[str, RunState] = {}
    app.state.broker = broker or broker_mod.BrokerClient()
    app.state.langfuse = langfuse or langfuse_mod.LangfuseClient()
    app.state.profile_root = profile_root or spawn_mod.DEFAULT_PROFILE_ROOT
    app.state.workspace_root = workspace_root or spawn_mod.DEFAULT_WORKSPACE_ROOT
    app.state.hermes_bin = hermes_bin or spawn_mod.DEFAULT_HERMES_BIN
    app.state.lock = asyncio.Lock()

    # -- helpers -----------------------------------------------------

    async def _monitor_run(state: RunState) -> None:
        """Drain stdout and publish terminal lifecycle event."""
        try:
            assert state.process.stdout is not None
            while True:
                chunk = await state.process.stdout.readline()
                if not chunk:
                    break
                state.output.append(chunk)
                for q in list(state.subscribers):
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(chunk)
            state.returncode = await state.process.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            _log.exception("run %s monitor crashed: %s", state.run_id, exc)
            state.returncode = state.returncode if state.returncode is not None else -1
        finally:
            for q in list(state.subscribers):
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(_EOF)
            state.done.set()

            rc = state.returncode if state.returncode is not None else -1
            event_type = "run.completed" if rc == 0 else "run.failed"
            try:
                await app.state.broker.publish_run_event(
                    event_type=event_type,
                    run_id=state.run_id,
                    session_id=state.session_id,
                    payload={
                        "profile": state.profile,
                        "returncode": rc,
                    },
                )
            except broker_mod.BrokerError as exc:
                _log.warning(
                    "broker publish %s for run %s failed: %s",
                    event_type,
                    state.run_id,
                    exc,
                )

            await app.state.langfuse.create_span(
                trace_id=state.run_id,
                name=event_type,
                level="DEFAULT" if rc == 0 else "ERROR",
                status_message=None if rc == 0 else f"returncode={rc}",
                metadata={"profile": state.profile, "returncode": rc},
            )

    # -- endpoints ---------------------------------------------------

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "runs_in_flight": len(app.state.runs)}

    @app.post("/runs/start", status_code=201, response_model=StartRunResponse)
    async def start_run(body: StartRunRequest) -> StartRunResponse:
        run_id = uuid.uuid4().hex
        try:
            plan = spawn_mod.build_spawn_plan(
                run_id=run_id,
                session_id=body.session_id,
                profile=body.profile,
                prompt=body.prompt,
                model=body.model,
                profile_root=app.state.profile_root,
                workspace_root=app.state.workspace_root,
                hermes_bin=app.state.hermes_bin,
            )
        except spawn_mod.SpawnRejected as exc:
            status = {
                "bad_request": 400,
                "forbidden": 403,
                "not_found": 404,
                "config": 500,
                "bad_env_file": 500,
            }.get(exc.reason, 400)
            raise HTTPException(status_code=status, detail={"reason": exc.reason, "detail": exc.detail}) from exc

        # Make sure the session AND run rows exist before the first
        # event lands — broker.events has FKs onto both and will 500
        # on run_id if we skip ensure_run.
        try:
            await app.state.broker.ensure_session(body.session_id)
        except broker_mod.BrokerError as exc:
            _log.warning("broker.ensure_session failed: %s", exc)

        try:
            await app.state.broker.ensure_run(
                run_id=run_id,
                session_id=body.session_id,
                metadata={"profile": body.profile, "model": body.model},
            )
        except broker_mod.BrokerError as exc:
            _log.warning("broker.ensure_run failed: %s", exc)

        try:
            await app.state.broker.publish_run_event(
                event_type="run.created",
                run_id=run_id,
                session_id=body.session_id,
                payload={"profile": body.profile, "model": body.model},
            )
        except broker_mod.BrokerError as exc:
            _log.warning("broker publish run.created failed: %s", exc)

        # Open a Langfuse trace keyed by run_id so subsequent spans and
        # broker events can be cross-referenced. No-op if Langfuse env
        # is not configured.
        await app.state.langfuse.create_trace(
            run_id=run_id,
            session_id=body.session_id,
            profile=body.profile,
            prompt=body.prompt,
            metadata={"model": body.model},
        )
        await app.state.langfuse.create_span(
            trace_id=run_id,
            name="run.created",
            metadata={"profile": body.profile, "model": body.model},
        )

        # asyncio subprocess gives us native async stream reading, no
        # thread pool round-trips required.
        proc = await asyncio.create_subprocess_exec(
            *plan.argv,
            env=plan.env,
            cwd=str(plan.cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )

        state = RunState(
            run_id=run_id,
            session_id=body.session_id,
            profile=body.profile,
            process=proc,
            plan=plan,
        )
        async with app.state.lock:
            app.state.runs[run_id] = state

        try:
            await app.state.broker.publish_run_event(
                event_type="run.started",
                run_id=run_id,
                session_id=body.session_id,
                payload={"profile": body.profile, "pid": proc.pid},
            )
        except broker_mod.BrokerError as exc:
            _log.warning("broker publish run.started failed: %s", exc)

        await app.state.langfuse.create_span(
            trace_id=run_id,
            name="run.started",
            metadata={"profile": body.profile, "pid": proc.pid},
        )

        asyncio.create_task(_monitor_run(state))

        _log.info(
            "started run %s (profile=%s pid=%s argv=%s)",
            run_id,
            body.profile,
            proc.pid,
            plan.pretty(),
        )
        return StartRunResponse(run_id=run_id, pid=proc.pid)

    @app.post("/runs/{run_id}/attach")
    async def attach_run(run_id: str, request: Request) -> StreamingResponse:
        state = app.state.runs.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id {run_id!r}")

        queue: asyncio.Queue[bytes | object] = asyncio.Queue(maxsize=10_000)
        # Replay already-captured output so late attachers don't miss
        # early stdout; then subscribe to live output.
        for chunk in list(state.output):
            queue.put_nowait(chunk)
        if state.done.is_set():
            queue.put_nowait(_EOF)
        state.subscribers.append(queue)

        async def _iter() -> AsyncIterator[bytes]:
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    item = await queue.get()
                    if item is _EOF:
                        payload = json.dumps(
                            {"returncode": state.returncode, "run_id": run_id}
                        )
                        yield f"event: end\ndata: {payload}\n\n".encode()
                        return
                    line = item if isinstance(item, bytes) else bytes(item)  # type: ignore[arg-type]
                    yield b"data: " + line.rstrip(b"\n") + b"\n\n"
            finally:
                with contextlib.suppress(ValueError):
                    state.subscribers.remove(queue)

        return StreamingResponse(_iter(), media_type="text/event-stream")

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> JSONResponse:
        state = app.state.runs.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id {run_id!r}")
        if state.done.is_set():
            return JSONResponse({"run_id": run_id, "status": "already_done", "returncode": state.returncode})
        try:
            os.killpg(state.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        return JSONResponse({"run_id": run_id, "status": "cancel_sent"})

    return app


# module-level app for ``uvicorn hermes_gateway.app:app --uds ...``
app = _build_app()
