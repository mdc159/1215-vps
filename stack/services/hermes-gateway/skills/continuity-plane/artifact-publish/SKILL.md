---
name: artifact-publish
description: Upload a file to MinIO and register it with the 1215 broker as an artifact. Emits an `artifact.registered` event, writes the `broker.artifacts` row, and returns the artifact_id + content-hash for downstream consumers. Idempotent on retry via sha256-derived idempotency key.
version: 1.0.0
metadata:
  hermes:
    tags: [continuity-plane, broker, artifacts, minio, s3]
    related_skills: [artifact-read, broadcast-publish]
---

# artifact_publish — upload a file and register it

## When to use

When you produce a durable artifact that other nodes or future runs
should be able to **fetch by ID**:

- A generated report / markdown document
- A workflow output JSON
- A memory extract (Honcho snapshot) for cross-node replay
- Any binary blob (image, PDF, trained model)

For ephemeral in-process data, use `broadcast_publish` (event payload)
instead — the artifact path is for things that need object storage.

## What it does

Three atomic steps, all idempotent:

1. **S3 PUT** to `s3://{bucket}/{node_id}/{artifact_id}-{filename}` on
   MinIO, signed with SigV4 via stdlib.
2. **`POST /events`** with `event_type=artifact.registered`, payload
   carrying `{artifact_id, uri, sha256, byte_length, mime_type, filename}`.
   Idempotency key is `artifact.registered:{sha256}` so replaying the
   same bytes reuses the original event row.
3. **`POST /artifacts`** with `storage_backend=minio` and the event we
   just wrote as `source_event_id`. Broker upserts on `(storage_backend, uri)`.

On exit the script prints a single JSON object with `artifact_id`,
`uri`, `sha256`, and the two broker rows. Feed this to `artifact-read`
or pass `artifact_id` in a downstream event payload.

## How to run

```bash
# Simple document upload
python3 scripts/artifact_publish.py \
  --file /tmp/q2-okrs.md \
  --artifact-kind document

# Workflow output with extra metadata
python3 scripts/artifact_publish.py \
  --file /tmp/run-output.json \
  --artifact-kind workflow-output \
  --metadata '{"workflow":"daily-standup","duration_ms":8421}'
```

## Contract

- `--artifact-kind` must exist in `broker.artifact_kinds`
  (`document`, `trace-export`, `workflow-output`, `memory-extract`,
  `blob`).
- The SHA-256 is computed locally **and** stored as both
  `checksum_sha256` (for integrity) and `source_event_hash` (for the
  FK into `broker.events.source_event_hash`). These always match.
- The script does not mutate or re-encode the file bytes; what you
  upload is what gets stored and hashed.

## Exit codes

- `0` — published.
- `2` — bad input, broker rejection, or MinIO auth issue.
- `3` — MinIO unreachable.

## Defaults

- `--broker-url` ← `$BROKER_URL`, else `http://127.0.0.1:8090`
- `--minio-endpoint` ← `$MINIO_ENDPOINT`, else `http://127.0.0.1:9010`
- `--bucket` ← `$MINIO_ARTIFACTS_BUCKET`, else `artifacts`
- MinIO credentials: `$MINIO_ACCESS_KEY` + `$MINIO_SECRET_KEY`, falling
  back to `$MINIO_ROOT_USER`/`$MINIO_ROOT_PASSWORD` from the prototype
  `.env`. The `orchestrator-ceo` profile `.env` is the supported
  injection point.
- `--node-id` ← `$HERMES_NODE_ID`, else `ceo-orchestrator`

## Files

- `scripts/artifact_publish.py` — entry point.
- `scripts/_s3.py` — stdlib SigV4 (no boto3 dependency).
