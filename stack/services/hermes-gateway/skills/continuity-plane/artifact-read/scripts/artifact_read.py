#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve a broker artifact and fetch (or presign) its bytes.

Modes:
  --presign   Print the broker row merged with a presigned GET URL.
  --download  Write the object bytes to --output (default: artifact_id).
  (default)   Print the broker row as JSON with signed_url included.

The broker stores ``uri = s3://{bucket}/{key}``; this script splits
that back into bucket+key, signs a time-limited GET against the
configured MinIO endpoint, and either emits the URL (safe to pass to
another process or to the user) or fetches the bytes locally.

Integrity check: if ``--verify-sha256`` is passed with ``--download``
we recompute sha256 on the downloaded bytes and compare against the
broker's ``checksum_sha256`` column. Mismatch is a non-zero exit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _s3 import S3Config, presign_get  # noqa: E402


def _default(env: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(env)
    return value if value else fallback


def _get_json(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _fetch_artifact_row(broker_url: str, artifact_id: str) -> dict | None:
    query = urllib.parse.urlencode({"artifact_id": artifact_id, "limit": "1"})
    status, body = _get_json(f"{broker_url.rstrip('/')}/artifacts?{query}")
    if status != 200:
        raise SystemExit(f"broker /artifacts rejected ({status}): {body}")
    rows = json.loads(body).get("artifacts", [])
    return rows[0] if rows else None


def _split_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise SystemExit(f"artifact.uri is not an s3:// URI: {uri!r}")
    without_scheme = uri[len("s3://"):]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        raise SystemExit(f"artifact.uri missing bucket or key: {uri!r}")
    return bucket, key


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and fetch a broker artifact.")
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--broker-url", default=_default("BROKER_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--minio-endpoint", default=_default("MINIO_ENDPOINT"))
    parser.add_argument("--expires", type=int, default=900,
                        help="Presigned-URL TTL in seconds (default 900 = 15 min).")
    parser.add_argument("--presign", action="store_true",
                        help="Only emit the presigned URL in the response; don't download.")
    parser.add_argument("--download", action="store_true",
                        help="Fetch the object bytes locally.")
    parser.add_argument("--output", default=None,
                        help="Local path for --download (default: ./<artifact_id>).")
    parser.add_argument("--verify-sha256", action="store_true",
                        help="With --download, recompute sha256 and compare against broker row.")
    args = parser.parse_args()

    row = _fetch_artifact_row(args.broker_url, args.artifact_id)
    if row is None:
        print(f"no artifact with id={args.artifact_id}", file=sys.stderr)
        return 4

    if row.get("storage_backend") != "minio":
        print(
            f"artifact storage_backend={row.get('storage_backend')!r}; "
            "this skill only resolves MinIO-backed artifacts.",
            file=sys.stderr,
        )
        return 5

    bucket, key = _split_s3_uri(row["uri"])

    try:
        config = S3Config(endpoint=args.minio_endpoint)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    signed_url = presign_get(config, bucket, key, expires=args.expires)
    row["signed_url"] = signed_url
    row["signed_url_expires_seconds"] = args.expires

    if args.download:
        output_path = pathlib.Path(args.output or args.artifact_id).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(signed_url, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            print(f"minio get failed ({exc.code}): {exc.read().decode()}", file=sys.stderr)
            return 3
        output_path.write_bytes(body)
        row["downloaded_to"] = str(output_path)
        row["downloaded_bytes"] = len(body)
        if args.verify_sha256:
            actual = hashlib.sha256(body).hexdigest()
            expected = row.get("checksum_sha256")
            row["sha256_match"] = actual == expected
            if actual != expected:
                print(
                    f"sha256 mismatch: expected={expected} actual={actual}",
                    file=sys.stderr,
                )
                json.dump(row, sys.stdout, indent=2, default=str)
                sys.stdout.write("\n")
                return 6

    json.dump(row, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
