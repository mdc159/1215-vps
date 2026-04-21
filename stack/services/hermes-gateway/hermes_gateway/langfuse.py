"""Minimal Langfuse ingestion client for the hermes-gateway.

Phase G correlates broker ``run_id`` with Langfuse ``trace_id`` — they
are the *same* UUID. When ``start_run`` mints a run, the gateway:

  1. Writes the broker row (``run.created``).
  2. Emits a Langfuse ``trace-create`` event keyed by ``id=run_id``.
  3. On each lifecycle event (``run.started``, ``run.completed``,
     ``run.failed``), emits an ``observation-create`` span nested under
     the trace.

The gateway only emits lifecycle spans — actual LLM-call spans would
need to live inside Hermes itself (out of scope for the prototype).
A multi-step run therefore shows up in Langfuse as a trace with 3–4
nested spans: created -> started -> completed / failed.

We talk to the ``/api/public/ingestion`` batch endpoint directly via
``httpx``. No ``langfuse`` package dependency, so the gateway stays on
stdlib + fastapi + httpx (already pinned). When the Langfuse env is
not configured (``_is_configured()`` returns False), every method is a
no-op so the gateway still runs in bare-stack prototypes that don't
expose Langfuse.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx


logger = logging.getLogger("hermes_gateway.langfuse")


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class LangfuseClient:
    """Thin async client over Langfuse ``/api/public/ingestion``.

    One instance per gateway process; reuses a single ``httpx.AsyncClient``
    so HTTP keep-alive is available for the per-run span stream.
    """

    def __init__(
        self,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
        *,
        project_name: str = "1215-hermes-gateway",
        timeout_seconds: float = 3.0,
    ) -> None:
        self._host = (host or os.environ.get("LANGFUSE_HOST") or "").rstrip("/")
        self._public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY") or ""
        self._secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY") or ""
        self._project_name = project_name
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    def _is_configured(self) -> bool:
        return bool(self._host and self._public_key and self._secret_key)

    async def __aenter__(self) -> "LangfuseClient":
        if self._is_configured():
            self._client = httpx.AsyncClient(
                auth=(self._public_key, self._secret_key),
                timeout=self._timeout,
            )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _send(self, events: list[dict[str, Any]]) -> None:
        """Batch-ingest events.

        We swallow all errors: Langfuse being down or misconfigured must
        never break run spawn. Instead we warn once per failure class
        and continue; the broker events are still the durable source of
        truth, so lost Langfuse spans degrade observability but not
        correctness.
        """
        if not self._is_configured() or self._client is None:
            return
        try:
            response = await self._client.post(
                f"{self._host}/api/public/ingestion",
                json={"batch": events},
            )
            if response.status_code >= 400:
                logger.warning(
                    "langfuse ingestion rejected batch: %s %s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.warning("langfuse ingestion unreachable: %s", exc)

    async def create_trace(
        self,
        *,
        run_id: str,
        session_id: str,
        profile: str,
        prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit the top-level trace row keyed by ``run_id``.

        Idempotent: re-ingesting a ``trace-create`` with the same ``id``
        is a no-op on Langfuse's side (the server deduplicates on
        ``(project_id, type, id)``).
        """
        body: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": _utcnow_iso(),
            "body": {
                "id": run_id,
                "timestamp": _utcnow_iso(),
                "name": f"hermes-run:{profile}",
                "sessionId": session_id,
                "input": {"prompt": prompt},
                "metadata": {
                    "profile": profile,
                    "project": self._project_name,
                    **(metadata or {}),
                },
            },
        }
        await self._send([body])

    async def create_span(
        self,
        *,
        trace_id: str,
        name: str,
        start_time: str | None = None,
        end_time: str | None = None,
        level: str = "DEFAULT",
        status_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a span (``observation-create`` with type SPAN).

        ``name`` is typically ``run.started`` / ``run.completed`` /
        ``run.failed`` so a Langfuse user can correlate the trace
        visualisation with the broker ``events`` feed.
        """
        now = _utcnow_iso()
        body: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": "observation-create",
            "timestamp": now,
            "body": {
                "id": str(uuid.uuid4()),
                "traceId": trace_id,
                "type": "SPAN",
                "name": name,
                "startTime": start_time or now,
                "endTime": end_time or now,
                "level": level,
                "statusMessage": status_message,
                "metadata": metadata or {},
            },
        }
        await self._send([body])
