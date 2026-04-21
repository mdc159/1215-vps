#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Upload a file to MinIO and register it with the 1215 broker.

Flow:
  1. Read the file, compute ``sha256`` (used as both the artifact hash
     and as part of the object key for content-addressed storage).
  2. PUT the bytes to ``s3://{bucket}/{node_id}/{artifact_id}``.
  3. POST ``/events`` with ``event_type=artifact.registered`` so the
     broker has a parent row for the FK on ``artifacts.source_event_id``.
  4. POST ``/artifacts`` with the storage location and parent event.

Both broker writes are idempotent:
- The event uses a stable idempotency_key derived from the sha256, so a
  retry after a partial failure reuses the original event row.
- The artifact row uses ``ON CONFLICT (storage_backend, uri) DO UPDATE``,
  so re-uploading the same object key updates the row instead of erroring.

Defaults assume the prototype-local substrate
(``stack/prototype-local/docker-compose.substrate.yml``): MinIO on
``127.0.0.1:9010``, bucket ``artifacts``, root user ``minio``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _s3 import S3Config, put_object  # noqa: E402


def _default(env: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(env)
    return value if value else fallback


def _post(broker_url: str, path: str, body: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        f"{broker_url.rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a file as a broker artifact.")
    parser.add_argument("--file", required=True, help="Path to the file to upload.")
    parser.add_argument("--artifact-kind", required=True,
                        help="One of: document, trace-export, workflow-output, memory-extract, blob.")
    parser.add_argument("--artifact-id", default=None,
                        help="Override auto-generated UUID artifact_id.")
    parser.add_argument("--bucket", default=_default("MINIO_ARTIFACTS_BUCKET", "artifacts"))
    parser.add_argument("--mime-type", default=None)
    parser.add_argument("--broker-url", default=_default("BROKER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--minio-endpoint", default=_default("MINIO_ENDPOINT"))
    parser.add_argument("--node-id", default=_default("HERMES_NODE_ID", "ceo-orchestrator"))
    parser.add_argument("--session-id", default=_default("HERMES_SESSION_ID"))
    parser.add_argument("--run-id", default=_default("HERMES_RUN_ID"))
    parser.add_argument("--metadata", default=None,
                        help='Optional JSON object merged into the broker artifact row.')
    args = parser.parse_args()

    path = pathlib.Path(args.file).expanduser()
    if not path.is_file():
        print(f"--file not found: {path}", file=sys.stderr)
        return 2
    body = path.read_bytes()
    sha256 = hashlib.sha256(body).hexdigest()

    artifact_id = args.artifact_id or str(uuid.uuid4())
    mime_type = args.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    metadata = json.loads(args.metadata) if args.metadata else {}
    if not isinstance(metadata, dict):
        raise SystemExit("--metadata must decode to a JSON object")

    object_key = f"{args.node_id}/{artifact_id}-{path.name}"

    try:
        config = S3Config(endpoint=args.minio_endpoint)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # --- 1) upload ------------------------------------------------------
    try:
        uri = put_object(config, args.bucket, object_key, body, content_type=mime_type)
    except Exception as exc:
        print(f"minio put failed: {exc}", file=sys.stderr)
        return 3

    # --- 2) register the parent event ----------------------------------
    occurred_at = datetime.now(tz=timezone.utc).isoformat()
    event_id = str(uuid.uuid4())
    event_body = {
        "event_id": event_id,
        "event_type": "artifact.registered",
        "payload_version": 1,
        "node_id": args.node_id,
        "session_id": args.session_id,
        "run_id": args.run_id,
        # sha256 is a stable key — retrying the publish with the same
        # bytes reuses the same event row instead of creating a new one.
        "idempotency_key": f"artifact.registered:{sha256}",
        "occurred_at": occurred_at,
        "payload_json": {
            "artifact_id": artifact_id,
            "artifact_kind": args.artifact_kind,
            "uri": uri,
            "sha256": sha256,
            "byte_length": len(body),
            "mime_type": mime_type,
            "filename": path.name,
        },
        "metadata_json": metadata,
    }
    status, event_raw = _post(args.broker_url, "/events", event_body)
    if status != 200:
        print(f"broker rejected artifact event ({status}): {event_raw}", file=sys.stderr)
        return 2
    event_row = json.loads(event_raw)["event"]
    # Re-use the broker's returned event_id: on idempotent replay the
    # broker returns the original row, which may not match our
    # client-minted event_id. The artifact row FKs against the stored
    # event_id, so we must defer to whatever the broker has.
    source_event_id = event_row["event_id"]

    # --- 3) register the artifact --------------------------------------
    artifact_body = {
        "artifact_id": artifact_id,
        "artifact_kind": args.artifact_kind,
        "source_event_id": source_event_id,
        "source_event_hash": sha256,
        "storage_backend": "minio",
        "uri": uri,
        "mime_type": mime_type,
        "checksum_sha256": sha256,
        "metadata_json": {
            "filename": path.name,
            "byte_length": len(body),
            "node_id": args.node_id,
            **metadata,
        },
    }
    status, artifact_raw = _post(args.broker_url, "/artifacts", artifact_body)
    if status != 200:
        print(f"broker rejected artifact row ({status}): {artifact_raw}", file=sys.stderr)
        return 2

    result = {
        "artifact": json.loads(artifact_raw)["artifact"],
        "event": event_row,
        "uri": uri,
        "sha256": sha256,
        "bucket": args.bucket,
        "object_key": object_key,
    }
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
