#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read the 1215 broker event feed with optional filters.

Wraps ``GET /events`` on the broker. Filters AND together on the
server side (see stack/broker/broker_service/app.py::list_events), so
combining ``--event-type`` with ``--run-id`` returns events that match
both. ``--after-seq`` is the replay-from-cursor primitive — pair it
with ``broadcast_ack`` to advance a provider checkpoint once the batch
is processed.

Output is the raw JSON envelope ``{"events": [...], "count": N}``
so the caller can pipe it to ``jq`` or another script without
re-parsing our formatting.
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the broker event feed.")
    parser.add_argument("--broker-url", default=_default("BROKER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--event-type", default=None,
                        help="Filter to one event_type (e.g. memory.published).")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--node-id", default=None)
    parser.add_argument("--after-seq", type=int, default=None,
                        help="Return only events with event_seq > N (for replay).")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max rows (broker caps at 500).")
    args = parser.parse_args()

    params: list[tuple[str, str]] = [("limit", str(args.limit))]
    if args.event_type: params.append(("event_type", args.event_type))
    if args.session_id: params.append(("session_id", args.session_id))
    if args.run_id: params.append(("run_id", args.run_id))
    if args.node_id: params.append(("node_id", args.node_id))
    if args.after_seq is not None: params.append(("after_seq", str(args.after_seq)))

    query = urllib.parse.urlencode(params)
    url = f"{args.broker_url.rstrip('/')}/events?{query}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        print(f"broker rejected read ({exc.code}): {exc.read().decode()}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"broker unreachable at {args.broker_url}: {exc}", file=sys.stderr)
        return 3

    # Pretty-print so Hermes sees a human-scannable feed by default;
    # if you're piping, use `--limit` + jq downstream.
    parsed = json.loads(body)
    json.dump(parsed, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
