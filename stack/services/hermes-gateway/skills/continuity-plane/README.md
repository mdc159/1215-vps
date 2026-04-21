# continuity-plane Hermes skills

First-party Hermes skills that wrap the 1215 continuity plane
(the broker + MinIO) so agents can participate in the cross-node
event / artifact / checkpoint protocol without speaking HTTP directly.

Installed into the `orchestrator-ceo` profile by
`stack/services/hermes-gateway/scripts/setup_ceo_profile.sh` (re-run
with `--force` to refresh).

## Layout

```
continuity-plane/
  broadcast-publish/        # POST /events  (emit a cross-node signal)
  broadcast-read-feed/      # GET  /events  (inspect or replay the feed)
  broadcast-ack/            # POST /checkpoints (advance replay cursor)
  artifact-publish/         # MinIO PUT + POST /events + POST /artifacts
  artifact-read/            # GET /artifacts + MinIO presigned GET
```

Each directory is a self-contained Hermes skill (a `SKILL.md` and a
`scripts/` helper). Skill directories are independent — `artifact-*`
ships its own stdlib SigV4 helper (`scripts/_s3.py`) rather than
sharing one, so copying a single skill to another profile is valid.

## Protocol contract

All five skills talk to the same two services:

- Broker: `$BROKER_URL`, default `http://127.0.0.1:8090`. Schema in
  [`stack/sql/broker/001_core.sql`](../../../../sql/broker/001_core.sql).
- MinIO: `$MINIO_ENDPOINT`, default `http://127.0.0.1:9010`. Root
  credentials come from the prototype-local `.env` via the profile's
  `HERMES_HOME/.env` (see `setup_ceo_profile.sh`).

Every write is idempotent on retry:

| Write                       | Idempotency key                          |
|-----------------------------|-------------------------------------------|
| `broadcast_publish`         | `(node_id, idempotency_key)` on events    |
| `artifact_publish` (event)  | `artifact.registered:{sha256}`            |
| `artifact_publish` (row)    | `(storage_backend, uri)`                  |
| `broadcast_ack`             | `(provider_name, node_id, checkpoint_kind)` + monotonic guard |

## Zero runtime dependencies

Skills are stdlib-only Python 3.11+. There is no `pip install` step,
no venv to maintain, no boto3 / httpx requirement. This is
deliberate: the hermes-gateway's spawn contract locks the child
`PATH` to `/usr/local/bin:/usr/bin:/bin:...` (see
`hermes_gateway/spawn.py::FIXED_PATH`), so packages installed in the
user's `~/.local/` venv wouldn't be reachable. Stdlib SigV4 for MinIO
and stdlib `urllib.request` for the broker sidestep that constraint.
