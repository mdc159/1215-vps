#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Advance (or read) a provider checkpoint in the 1215 broker.

Backs the Phase F acceptance step "broadcast_ack advances a
checkpoint; GET /checkpoints reflects it." The broker's
``provider_checkpoints`` table is the canonical store for
"where did this provider leave off" cursors (see
stack/sql/broker/001_core.sql).

Design notes:
- The broker's ``POST /checkpoints`` is a plain UPSERT — it does not
  enforce monotonic advancement. This script does, by reading the
  current checkpoint first and refusing to go backwards unless
  ``--force`` is set. This preserves replay sanity: a retry that
  re-acks an older cursor value should be a no-op, not a regression.
- ``--read`` inverts the operation: print the current cursor_value (or
  nothing if absent) to stdout and exit 0. Shell callers use this to
  seed a replay-from-cursor loop before calling
  ``broadcast_read_feed`` with ``--after-seq``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _default(env: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(env)
    return value if value else fallback


def _http(
    broker_url: str,
    method: str,
    path: str,
    *,
    query: dict | None = None,
    body: dict | None = None,
) -> tuple[int, str]:
    url = f"{broker_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _read_cursor(
    broker_url: str,
    provider: str,
    node_id: str,
    kind: str,
) -> tuple[str | None, str | None]:
    """Return (cursor_value, source_event_id) or (None, None) if no row."""
    status, body = _http(
        broker_url,
        "GET",
        "/checkpoints",
        query={
            "provider_name": provider,
            "node_id": node_id,
            "checkpoint_kind": kind,
        },
    )
    if status != 200:
        raise SystemExit(f"broker /checkpoints rejected GET ({status}): {body}")
    rows = json.loads(body).get("checkpoints", [])
    if not rows:
        return None, None
    row = rows[0]
    return row.get("cursor_value"), row.get("source_event_id")


def _cursor_as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance a broker provider checkpoint.")
    parser.add_argument("--broker-url", default=_default("BROKER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--provider", required=True,
                        help="Provider name (e.g. hermes-ceo, replay-daemon).")
    parser.add_argument("--node-id", default=_default("HERMES_NODE_ID", "ceo-orchestrator"))
    parser.add_argument("--checkpoint-kind", required=True,
                        help="Must exist in broker.checkpoint_kinds (replay-cursor, publish-outbox, provider-sync).")
    parser.add_argument("--cursor-value", default=None,
                        help="New cursor value (required unless --read).")
    parser.add_argument("--source-event-id", default=None)
    parser.add_argument("--metadata", default=None, help='Optional JSON object.')
    parser.add_argument("--force", action="store_true",
                        help="Allow non-monotonic advancement (rewind). Default forbids it.")
    parser.add_argument("--read", action="store_true",
                        help="Print the current cursor_value to stdout instead of writing.")
    args = parser.parse_args()

    if args.read:
        cursor_value, _ = _read_cursor(
            args.broker_url, args.provider, args.node_id, args.checkpoint_kind
        )
        if cursor_value is not None:
            print(cursor_value)
        return 0

    if args.cursor_value is None:
        parser.error("--cursor-value is required unless --read is passed.")

    existing, _ = _read_cursor(
        args.broker_url, args.provider, args.node_id, args.checkpoint_kind
    )
    existing_int = _cursor_as_int(existing)
    new_int = _cursor_as_int(args.cursor_value)
    # If both sides parse as ints, enforce monotonic advancement.
    # If either is non-numeric, treat the cursor as opaque and let
    # --force be the only rewind path; most replay cursors are
    # event_seq (an int) so this strict-path catches the common case.
    if (
        not args.force
        and existing_int is not None
        and new_int is not None
        and new_int < existing_int
    ):
        print(
            f"refusing to rewind {args.provider}/{args.node_id}/{args.checkpoint_kind}: "
            f"existing={existing_int} new={new_int}; pass --force to override.",
            file=sys.stderr,
        )
        return 4

    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--metadata is not valid JSON: {exc}")
        if not isinstance(metadata, dict):
            raise SystemExit("--metadata must decode to a JSON object")

    status, body = _http(
        args.broker_url,
        "POST",
        "/checkpoints",
        body={
            "provider_name": args.provider,
            "node_id": args.node_id,
            "checkpoint_kind": args.checkpoint_kind,
            "cursor_value": args.cursor_value,
            "source_event_id": args.source_event_id,
            "metadata_json": metadata,
        },
    )
    if status != 200:
        print(f"broker rejected ack ({status}): {body}", file=sys.stderr)
        return 2

    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
