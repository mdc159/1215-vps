---
name: artifact-read
description: Resolve a broker artifact by ID and either return a presigned MinIO URL or download the bytes locally (with optional sha256 integrity check). Use this to inspect artifacts produced by artifact-publish or by other nodes.
version: 1.0.0
metadata:
  hermes:
    tags: [continuity-plane, broker, artifacts, minio, s3]
    related_skills: [artifact-publish, broadcast-read-feed]
---

# artifact_read — resolve and fetch a broker artifact

## When to use

- Another agent (or a past run of the CEO) wrote an artifact you need
  to inspect. `GET /artifacts` gave you an `artifact_id`; now you want
  either the bytes or a short-lived URL to hand to something else.
- Paperclip or an n8n workflow needs to embed the artifact somewhere;
  give it the presigned URL with `--presign`.

## Two modes

**Presign only** — useful when you want the URL, not the bytes:

```bash
python3 scripts/artifact_read.py \
  --artifact-id 3f8c...bde9 \
  --presign \
  --expires 600
```

Returns the full broker row plus `signed_url` and
`signed_url_expires_seconds`.

**Download** — fetch the object locally and optionally verify:

```bash
python3 scripts/artifact_read.py \
  --artifact-id 3f8c...bde9 \
  --download \
  --output /tmp/artifact.md \
  --verify-sha256
```

## Exit codes

- `0` — resolved (or downloaded + verified).
- `2` — missing MinIO credentials / bad input.
- `3` — MinIO unreachable or GET failed.
- `4` — no artifact with that id in the broker.
- `5` — artifact has `storage_backend != minio` (this skill only
  handles MinIO-backed artifacts; other backends would need their own
  read skill).
- `6` — `--verify-sha256` was passed and the recomputed hash didn't
  match `checksum_sha256`. The partial download is still written, but
  the row includes `sha256_match: false` so callers can react.

## Defaults

- `--broker-url` ← `$BROKER_URL`, else `http://127.0.0.1:8090`
- `--minio-endpoint` ← `$MINIO_ENDPOINT`, else `http://127.0.0.1:9010`
- MinIO credentials: `$MINIO_ACCESS_KEY`/`$MINIO_SECRET_KEY`, fallback
  to `$MINIO_ROOT_USER`/`$MINIO_ROOT_PASSWORD`.
- `--expires` default is 900s (15 min). URLs are ephemeral by design —
  the broker row is the canonical reference, not the URL.

## Files

- `scripts/artifact_read.py` — entry point.
- `scripts/_s3.py` — stdlib SigV4 (shared with `artifact-publish`).
