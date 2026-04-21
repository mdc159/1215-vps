"""Minimal S3 client — stdlib-only SigV4.

Intentionally no boto3 dependency: Hermes skills may run in spawned
subprocesses whose PATH does not reach the user's uv/venv (see
stack/services/hermes-gateway/hermes_gateway/spawn.py::FIXED_PATH).
Keeping this stdlib-only means the artifact-publish / artifact-read
scripts work identically under `python3 scripts/...` and under any
future sandboxed runtime we pick.

Implements the single endpoint pattern (``http://127.0.0.1:9010``) that
the MinIO ``local`` alias in the prototype substrate exposes. Both the
real AWS regional SigV4 and MinIO's equivalent accept ``us-east-1`` as
the default region, which is why we hardcode that below.

This module is duplicated into both artifact-publish and artifact-read
skill directories so each skill can be copied to another host as a
self-contained unit (Hermes skill convention).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


_DEFAULT_ENDPOINT = "http://127.0.0.1:9010"
_REGION = "us-east-1"
_SERVICE = "s3"
_ALGO = "AWS4-HMAC-SHA256"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, date: str) -> bytes:
    k_date = _sign(f"AWS4{secret}".encode(), date)
    k_region = _sign(k_date, _REGION)
    k_service = _sign(k_region, _SERVICE)
    return _sign(k_service, "aws4_request")


def _canon_query(query: dict[str, str]) -> str:
    # Canonical query string: sorted by key, each value RFC3986-encoded.
    # We use ``safe=""`` so ``/`` in expires-signed URLs is encoded too.
    items = sorted(query.items())
    return "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in items
    )


class S3Config:
    """Resolved MinIO / S3 endpoint + credentials."""

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = _REGION,
    ) -> None:
        self.endpoint = (endpoint or os.environ.get("MINIO_ENDPOINT") or _DEFAULT_ENDPOINT).rstrip("/")
        self.access_key = access_key or os.environ.get("MINIO_ACCESS_KEY") or os.environ.get("MINIO_ROOT_USER", "minio")
        self.secret_key = secret_key or os.environ.get("MINIO_SECRET_KEY") or os.environ.get("MINIO_ROOT_PASSWORD")
        if not self.secret_key:
            raise RuntimeError(
                "MinIO secret not set. Export MINIO_SECRET_KEY (or MINIO_ROOT_PASSWORD) in the "
                "Hermes profile .env. See stack/prototype-local/.env."
            )
        self.region = region

    @property
    def host(self) -> str:
        return urllib.parse.urlparse(self.endpoint).netloc


def put_object(
    config: S3Config,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str | None = None,
) -> str:
    """Upload ``body`` to ``s3://{bucket}/{key}``; return the s3:// URI."""
    now = datetime.now(tz=timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    url_path = f"/{bucket}/{urllib.parse.quote(key, safe='/')}"
    headers = {
        "host": config.host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        headers["content-type"] = content_type

    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(
        f"{name}:{value}\n" for name, value in sorted(headers.items())
    )
    canonical_request = (
        f"PUT\n{url_path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    credential_scope = f"{date_stamp}/{config.region}/{_SERVICE}/aws4_request"
    string_to_sign = (
        f"{_ALGO}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )
    signature = hmac.new(
        _signing_key(config.secret_key, date_stamp),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{_ALGO} Credential={config.access_key}/{credential_scope},"
        f"SignedHeaders={signed_headers},Signature={signature}"
    )

    request = urllib.request.Request(
        f"{config.endpoint}{url_path}",
        data=body,
        method="PUT",
        headers={
            # urllib normalises header names; preserve the already-signed
            # values (MinIO accepts case-insensitive headers, but the
            # SigV4 canonical form above already fixed the lowercase set).
            "Authorization": authorization,
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            **({"Content-Type": content_type} if content_type else {}),
            "Host": config.host,
            "Content-Length": str(len(body)),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"s3 put failed: {response.status} {response.read()!r}")

    return f"s3://{bucket}/{key}"


def presign_get(
    config: S3Config,
    bucket: str,
    key: str,
    expires: int = 900,
) -> str:
    """Return a presigned GET URL valid for ``expires`` seconds.

    Used by artifact-read to give Hermes a short-lived fetch URL without
    handing out the MinIO root secret. 15 minutes (900s) is the default
    because it's long enough for a single CEO turn to inspect the
    artifact but short enough that leaked URLs age out quickly.
    """
    now = datetime.now(tz=timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{config.region}/{_SERVICE}/aws4_request"
    url_path = f"/{bucket}/{urllib.parse.quote(key, safe='/')}"

    query: dict[str, str] = {
        "X-Amz-Algorithm": _ALGO,
        "X-Amz-Credential": f"{config.access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = _canon_query(query)
    canonical_request = (
        f"GET\n{url_path}\n{canonical_query}\n"
        f"host:{config.host}\n\nhost\nUNSIGNED-PAYLOAD"
    )
    string_to_sign = (
        f"{_ALGO}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )
    signature = hmac.new(
        _signing_key(config.secret_key, date_stamp),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    query["X-Amz-Signature"] = signature
    return f"{config.endpoint}{url_path}?{_canon_query(query)}"
