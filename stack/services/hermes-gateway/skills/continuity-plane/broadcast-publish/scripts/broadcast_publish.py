#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Publish a broker event from within a Hermes run.

Thin wrapper around ``POST /events`` on the 1215 broker. This is the
Hermes-facing entry point; everything else in the continuity plane (the
gateway, Paperclip, replay-from-cursor) observes the event via the
broker rather than talking to Hermes directly.

Design notes:
- Stdlib-only on purpose. Hermes ships multiple Python toolchains and
  scripts that require pip installs break sporadically on first run.
- All IDs except ``event_id`` and ``idempotency_key`` are caller-provided.
  When not provided they default to ``HERMES_*`` env vars set by the
  gateway's spawn contract (see stack/services/hermes-gateway/hermes_gateway/spawn.py).
- ``idempotency_key`` auto-defaults to a stable hash of
  ``(event_type, run_id or session_id or occurred_at, payload_sha256)``
  so retrying the same call is a no-op at the broker.
- The broker enforces ``UNIQUE (node_id, idempotency_key)`` so a retry
  after a partial failure (e.g. process killed mid-POST) will return the
  original event row instead of duplicating it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


def _default(env: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(env)
    return value if value else fallback


def _stable_idempotency_key(event_type: str, scope: str, payload: dict) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(payload_bytes).hexdigest()[:16]
    return f"{event_type}:{scope}:{digest}"


def _parse_payload(raw: str) -> dict:
    if raw.startswith("@"):
        with open(raw[1:], encoding="utf-8") as handle:
            raw = handle.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--payload is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit("--payload must decode to a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a broker event.")
    parser.add_argument("--broker-url", default=_default("BROKER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--event-type", required=True,
                        help="Must exist in broker.event_types (e.g. memory.published).")
    parser.add_argument("--payload", required=True,
                        help='Inline JSON object, or "@path/to/file.json".')
    parser.add_argument("--payload-version", type=int, default=1)
    parser.add_argument("--node-id", default=_default("HERMES_NODE_ID", "ceo-orchestrator"))
    parser.add_argument("--session-id", default=_default("HERMES_SESSION_ID"))
    parser.add_argument("--run-id", default=_default("HERMES_RUN_ID"))
    parser.add_argument("--event-id", default=None,
                        help="Override auto-generated UUID event_id.")
    parser.add_argument("--idempotency-key", default=None,
                        help="Override auto-derived key. Must be unique per (node_id, key).")
    parser.add_argument("--source-event-id", default=None)
    parser.add_argument("--source-event-hash", default=None)
    parser.add_argument("--occurred-at", default=None,
                        help="ISO-8601. Defaults to now() in UTC.")
    parser.add_argument("--metadata", default=None,
                        help='Optional JSON object, or "@path/to/file.json".')
    args = parser.parse_args()

    payload = _parse_payload(args.payload)
    metadata = _parse_payload(args.metadata) if args.metadata else {}

    occurred_at = args.occurred_at or datetime.now(tz=timezone.utc).isoformat()
    scope = args.run_id or args.session_id or occurred_at
    idem = args.idempotency_key or _stable_idempotency_key(args.event_type, scope, payload)

    body = {
        "event_id": args.event_id or str(uuid.uuid4()),
        "event_type": args.event_type,
        "payload_version": args.payload_version,
        "node_id": args.node_id,
        "session_id": args.session_id,
        "run_id": args.run_id,
        "idempotency_key": idem,
        "source_event_id": args.source_event_id,
        "source_event_hash": args.source_event_hash,
        "occurred_at": occurred_at,
        "payload_json": payload,
        "metadata_json": metadata,
    }

    request = urllib.request.Request(
        f"{args.broker_url.rstrip('/')}/events",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode()
    except urllib.error.HTTPError as exc:
        # Surface the broker's validation error verbatim so operators can
        # diagnose bad payloads without tailing the broker's logs.
        print(f"broker rejected event ({exc.code}): {exc.read().decode()}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"broker unreachable at {args.broker_url}: {exc}", file=sys.stderr)
        return 3

    print(response_body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
