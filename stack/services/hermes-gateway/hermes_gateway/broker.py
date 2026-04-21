"""HTTP client that publishes lifecycle events to the broker.

The broker at http://127.0.0.1:8090 owns the durable event log. The
gateway has one job here: per Hermes run, publish a clean timeline of
``run.created`` -> ``run.started`` -> ``run.completed`` | ``run.failed``
so downstream nodes (Paperclip UI, Langfuse ingest in Phase G) can
stitch together what happened.

Design:

- Async (httpx.AsyncClient) — the gateway is FastAPI, so every call
  the app layer makes is already in an event loop.
- Idempotent everywhere. The broker itself short-circuits duplicates
  by primary key / idempotency_key, so we can safely replay events
  after a crash without poisoning the timeline.
- Stateless. The client doesn't cache anything; it just constructs
  the right JSON and fires it. Any per-run state the app needs lives
  on the SpawnHandle.

Idempotency key scheme:

    run.created    -> "{run_id}:created"
    run.started    -> "{run_id}:started"
    run.completed  -> "{run_id}:completed"
    run.failed     -> "{run_id}:failed"

This lets a crashed gateway restart and re-publish ``run.failed`` for
runs that never finished without creating duplicate terminal events.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

_log = logging.getLogger(__name__)

DEFAULT_BROKER_URL = "http://127.0.0.1:8090"
DEFAULT_NODE_ID = "hermes-gateway"
DEFAULT_NODE_ROLE = "gateway"
DEFAULT_NODE_DISPLAY_NAME = "hermes-gateway (host)"
DEFAULT_SURFACE = "hermes-gateway"

RunEventType = Literal["run.created", "run.started", "run.completed", "run.failed"]


class BrokerError(RuntimeError):
    """Broker returned a non-2xx status we can't recover from.

    The app layer catches this, emits a structured log line, and
    returns 502 to the caller so Paperclip can decide whether to
    retry. We do NOT fail the spawn if the broker is unreachable on
    ``run.created``: the Hermes subprocess must still run, and a
    reconcile job can backfill continuity from the event log later.
    """


class BrokerClient:
    """Small async HTTP client for broker /nodes, /sessions, /events.

    The broker already handles idempotency, so this class is a thin
    envelope. Keep it minimal: it's the one boundary between the
    gateway's in-memory state and the durable continuity plane.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BROKER_URL,
        node_id: str = DEFAULT_NODE_ID,
        node_role: str = DEFAULT_NODE_ROLE,
        node_display_name: str = DEFAULT_NODE_DISPLAY_NAME,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.node_role = node_role
        self.node_display_name = node_display_name
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout
        )
        # httpx respects base_url iff we're using the instance-owned
        # client. If the caller injected their own, we'll compose URLs
        # ourselves.
        if http_client is not None and not str(http_client.base_url).rstrip("/"):
            self._client = http_client

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- low-level wrappers ---------------------------------------------

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = path if str(self._client.base_url).rstrip("/") else f"{self.base_url}{path}"
        try:
            resp = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise BrokerError(f"broker POST {path} failed: {exc}") from exc
        if resp.status_code >= 300:
            raise BrokerError(
                f"broker POST {path} -> {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {}

    # -- public API ------------------------------------------------------

    async def ensure_node(self) -> None:
        """Upsert the gateway's node row. Safe to call on every startup."""
        await self._post(
            "/nodes",
            {
                "node_id": self.node_id,
                "node_role": self.node_role,
                "display_name": self.node_display_name,
            },
        )

    async def ensure_session(
        self, session_id: str, *, surface: str = DEFAULT_SURFACE
    ) -> None:
        """Register a session keyed by ``session_id``. Safe to replay."""
        await self._post(
            "/sessions",
            {
                "session_id": session_id,
                "node_id": self.node_id,
                "surface": surface,
            },
        )

    async def publish_run_event(
        self,
        *,
        event_type: RunEventType,
        run_id: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Publish a run lifecycle event.

        ``idempotency_key`` is derived from ``run_id`` + ``event_type``
        so the broker coalesces retries. ``event_id`` is a fresh UUID
        (the broker uses that as the primary key of the event row).
        """
        if not run_id or not session_id:
            raise ValueError("run_id and session_id are required")
        occurred = occurred_at or datetime.now(timezone.utc)
        body = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "payload_version": 1,
            "node_id": self.node_id,
            "session_id": session_id,
            "run_id": run_id,
            "idempotency_key": f"{run_id}:{event_type.split('.', 1)[1]}",
            "occurred_at": occurred.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "payload_json": payload or {},
        }
        await self._post("/events", body)
