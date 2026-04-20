# prototype-local

`prototype-local` is the first runnable local-node implementation for the 1215
architecture. It is not a throwaway dev stack. It exists to validate the
shared continuity contracts, localhost-only exposure model, and the service mix
before hardening the VPS hub.

## Scope of the first substrate slice

This initial compose focuses on the foundational local services:

- Broker API
- Postgres
- Valkey
- MinIO
- Qdrant
- Neo4j
- ClickHouse
- Langfuse
- Open WebUI
- n8n
- Optional `n8n-mcp` `tools` profile
- Optional ComfyUI `media` profile

It does **not** yet include:

- Paperclip
- Hermes gateway
- Honcho

Those are added after the substrate is validated.

## Bring-up

```bash
docker compose -f stack/prototype-local/docker-compose.substrate.yml up -d
docker compose -f stack/prototype-local/docker-compose.substrate.yml ps
./bin/start-1215.py broker-files
./bin/start-1215.py broker-apply --target prototype-local
curl http://127.0.0.1:8090/healthz
```

All ports bind to `127.0.0.1` only in this first slice.

## Entry points

Current local entry points for the validated prototype path:

- Broker API: `http://127.0.0.1:8090`
- Open WebUI UI/API: `http://127.0.0.1:8080`
- n8n UI/API: `http://127.0.0.1:5678`
- Prototype `n8n` webhook: `http://127.0.0.1:5678/webhook/prototype-postgres-tables`
- MinIO S3 API: `http://127.0.0.1:9010`
- MinIO Console: `http://127.0.0.1:9011`
- Prototype MinIO webhook: `http://127.0.0.1:5678/webhook/prototype-minio-buckets`
- Optional `n8n-mcp` HTTP server: `http://127.0.0.1:13000`
- Optional ComfyUI UI/API: `http://127.0.0.1:8188`

Repo-owned workflow and function artifacts:

- Open WebUI pipe: [stack/prototype-local/open-webui/functions/prototype_n8n_pipe.py](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/open-webui/functions/prototype_n8n_pipe.py)
- n8n manual smoke workflow: [stack/prototype-local/n8n/Get_Prototype_Postgres_Tables.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Get_Prototype_Postgres_Tables.json)
- n8n webhook smoke workflow: [stack/prototype-local/n8n/Get_Prototype_Postgres_Tables_Webhook.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Get_Prototype_Postgres_Tables_Webhook.json)
- n8n MinIO webhook smoke workflow: [stack/prototype-local/n8n/List_Prototype_Minio_Buckets_Webhook.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/List_Prototype_Minio_Buckets_Webhook.json)
- n8n ComfyUI smoke workflow: [stack/prototype-local/n8n/Get_Prototype_ComfyUI_System_Stats_Webhook.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Get_Prototype_ComfyUI_System_Stats_Webhook.json)
- n8n ComfyUI SD1.5 queue workflow: [stack/prototype-local/n8n/Queue_Prototype_ComfyUI_SD15_Webhook.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Queue_Prototype_ComfyUI_SD15_Webhook.json)
- n8n ComfyUI SD1.5 artifact workflow: [stack/prototype-local/n8n/Generate_Prototype_ComfyUI_SD15_Artifact_Webhook.json](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Generate_Prototype_ComfyUI_SD15_Artifact_Webhook.json)

The currently validated E2E path is:

1. Open WebUI `pipe` model `prototype_n8n_pipe`
2. `POST` request to the local `n8n` webhook
3. `n8n` upserts the broker node, upserts the continuity session, starts and completes a broker run, and records a `workflow.completed` broker event
4. `n8n` queries Postgres and returns both the table summary and continuity IDs
5. assistant response returned through Open WebUI `/api/chat/completions`

The currently validated media/storage path is:

1. `n8n` runs with local `ffmpeg` and `ffprobe` available in the container
2. MinIO exposes `artifacts` and `langfuse` buckets on the local Docker network
3. `n8n` S3 credential `Prototype Local MinIO` points at `http://minio:9000`
4. `GET /webhook/prototype-minio-buckets` returns the live MinIO bucket list
5. `shared-data-init` prepares `/data/shared/prototype-media` so containerized
   media workflows can write artifacts before upload
6. `n8n` widens `N8N_RESTRICT_FILE_ACCESS_TO` to include `/data/shared`
7. `n8n` sets `N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=false` so `Read Binary File`
   can consume media generated under `~/.n8n-files/prototype-media` before S3
   upload

## Media surfaces

The intended split is:

- ComfyUI: media generation surface
- `n8n` + `ffmpeg`: orchestration, transcoding, thumbnails, muxing, and post-processing
- MinIO: durable local artifact exchange instead of opaque Docker-volume-only handoff

This prevents generation, processing, and storage from collapsing into a single
tool boundary.

## Optional n8n-mcp profile

The compose file includes an optional `n8n-mcp` service under the `tools`
profile. Start it only when you want MCP-based node discovery and workflow
management against the local `n8n` instance:

```bash
docker compose --env-file stack/prototype-local/.env \
  -f stack/prototype-local/docker-compose.substrate.yml \
  --profile tools up -d n8n-mcp
```

Current local assumptions:

- `n8n-mcp` listens on `http://127.0.0.1:13000`
- it reaches local `n8n` over the Docker network at `http://n8n:5678`
- it uses `N8N_API_KEY` from `stack/prototype-local/.env` for management tools
- it uses `N8N_MCP_AUTH_TOKEN` for HTTP-mode auth
- MCP clients still need to connect to it explicitly; starting the server does
  not hot-register tools into an already-running Codex session

Important behavior:

- `n8n-mcp` helps with discovery, schema-aware authoring, and workflow
  management
- it does **not** register missing runtime nodes inside the `n8n` process
- if a node is absent from the active `n8n` runtime catalog, `n8n-mcp` will
  not make that workflow executable by itself

### n8n media notes

The local `n8n` image is built from [stack/prototype-local/n8n/Dockerfile](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n/Dockerfile).
It copies static `ffmpeg` and `ffprobe` binaries into the official `n8n`
image. This is intentional: the current hardened `n8n` image in this stack does
not include `apk`, so `apk add --no-cache ffmpeg` is not a valid local fix.

The base `n8n` image is pinned through `N8N_BASE_IMAGE` in
`stack/prototype-local/.env`. Default is `n8nio/n8n:latest`, but this makes it
easy to freeze to a late `1.x` image if `2.x` hardening or runtime regressions
block required local workflows.

### MinIO artifact notes

Buckets created automatically at startup:

- `artifacts`
- `langfuse`

Important behavior:

- Treat MinIO as the durable local artifact boundary for media workflows.
- Do not rely on container-internal output paths as the only artifact store.
- For `n8n`-local media generation, use `~/.n8n-files/prototype-media` as the
  scratch path. `n8n` 2.x blocks reads from its own files directory by default,
  so the compose stack explicitly disables that internal block for this local
  prototype.
- `N8N_RESTRICT_FILE_ACCESS_TO` uses semicolon-separated paths, not commas.
  The local stack uses `~/.n8n-files;/data/shared`.
- Reserve `/data/shared` for cross-container handoff with tools like ComfyUI or
  other media workers that should not depend on `n8n`'s private files area.
- `n8n` credential IDs are instance-local. Preserve credential names in repo
  artifacts and remap IDs at import time if a workflow references credentials.

### Optional ComfyUI profile

The compose file includes an optional `comfyui` service under the `media`
profile. Start it only when needed:

```bash
docker compose --env-file stack/prototype-local/.env \
  -f stack/prototype-local/docker-compose.substrate.yml \
  --profile media up -d comfyui
```

This keeps ComfyUI available as a first-class generator surface without making
the baseline substrate depend on a heavy GPU-oriented service.

ComfyUI model weights should live on the dedicated ComfyUI models volume, not
in MinIO as the primary runtime store. MinIO is the durable exchange layer for
generated artifacts, exports, and optional model distribution or backup.

Current local behavior:

- `prototype-local` boots ComfyUI with `--cpu` by default because this host
  does not expose an NVIDIA driver into Docker.
- That is good enough for API smoke tests and workflow wiring, but not for
  practical image generation throughput.
- When a GPU-backed host is available, remove the `--cpu` command flag or
  replace it with the appropriate device/runtime settings before treating
  ComfyUI as a production-grade generator surface.
- The first SD1.5 workflow should stay small: queue a minimal prompt graph and
  return either a `promptId` or ComfyUI's checkpoint validation error. Do not
  assume a model is installed until `CheckpointLoaderSimple` exposes one.
- The next SD1.5 workflow can build on that queue path by polling
  `/history/{prompt_id}`, downloading `/view`, and uploading the finished image
  into MinIO under `prototype-comfyui/`.

## Recovery

### Open WebUI first-run admin bootstrap

If `http://127.0.0.1:8080/api/config` returns `"onboarding": true`, the first
successful `POST /api/v1/auths/signup` becomes the admin user and disables
signup afterwards.

Minimal bootstrap flow:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auths/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "admin@example.local",
    "password": "replace-me",
    "name": "Admin",
    "profile_image_url": ""
  }'
```

### Open WebUI password recovery

Do not commit live passwords into the repo. Reset the local admin password in
SQLite, then sign in normally through the public API.

Generate a bcrypt hash:

```bash
python3 - <<'PY'
import bcrypt
print(bcrypt.hashpw(b'NewPassword123!', bcrypt.gensalt()).decode())
PY
```

Update the local Open WebUI auth row:

```bash
docker compose --env-file stack/prototype-local/.env \
  -f stack/prototype-local/docker-compose.substrate.yml \
  exec -T open-webui sh -lc "python - <<'PY'
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute(
    \"update auth set password=? where email=?\",
    ('<bcrypt-hash>', 'prototype-admin@example.local'),
)
conn.commit()
print(cur.rowcount)
PY"
```

Then sign in again:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auths/signin \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "prototype-admin@example.local",
    "password": "NewPassword123!"
  }'
```

### Open WebUI function import/update

Admin API endpoints used successfully against `v0.7.2`:

- `POST /api/v1/functions/create`
- `POST /api/v1/functions/id/{id}/update`
- `POST /api/v1/functions/id/{id}/toggle`
- `POST /api/v1/functions/id/{id}/valves/update`
- `GET /api/models`
- `POST /api/chat/completions`

Important behavior:

- If `chat_id`, `session_id`, and `message_id` are present, Open WebUI may
  return a background task envelope instead of the final completion.
- For direct smoke tests, omit those fields and call `/api/chat/completions`
  synchronously.

### n8n recovery and import notes

Useful local runtime checks:

```bash
docker compose --env-file stack/prototype-local/.env \
  -f stack/prototype-local/docker-compose.substrate.yml ps

curl http://127.0.0.1:8090/healthz
curl -X POST http://127.0.0.1:5678/webhook/prototype-postgres-tables \
  -H 'Content-Type: application/json' \
  -d '{"chatInput":"show prototype tables","sessionId":"demo-session","messageId":"demo-message","userId":"demo-user"}'
curl http://127.0.0.1:5678/webhook/prototype-minio-buckets
```

Known gotchas already hit in this stack:

- The broker must use structured Postgres env vars, not a raw URL with an
  unescaped generated password embedded in it.
- `n8n` webhook method must match the node registration. The current prototype
  Open WebUI workflow is registered for `POST`, while the MinIO bucket smoke
  workflow is registered for `GET`.
- There is a known `n8n` API/webhook creation issue around webhook
  registration metadata. If a webhook workflow is created or mutated by API and
  does not register properly, confirm the webhook node includes a stable
  `webhookId` and that the runtime method matches the node configuration.
- The `n8n` CLI import commands require real file paths. They do not accept
  `--input=-`, so stdin-based imports fail with `ENOENT`.

## Agent onboarding

When Paperclip or Hermes join the workflow layer, prefer these entry points
instead of ad hoc UI-only setup:

- Broker-facing continuity work: call the broker API on `:8090`
- Workflow automation and tool handoff: call the `n8n` webhook on `:5678`
- Human-facing agent shell: use Open WebUI on `:8080`
- Media generation: use ComfyUI on `:8188` when the `media` profile is enabled
- Durable media artifacts: use MinIO on `:9010`

Recommended onboarding pattern:

1. Keep reusable workflow logic in repo-owned `n8n` JSON under
   `stack/prototype-local/n8n/`.
2. Keep Open WebUI entry functions in repo-owned Python under
   `stack/prototype-local/open-webui/functions/`.
3. Treat Open WebUI `pipe` models as thin ingress adapters, not as the system
   of record.
4. Move durable state changes and cross-agent continuity events into the broker,
   even if the initial user hop goes through Open WebUI and `n8n`.
5. When a new workflow is meant for Hermes or Paperclip, give it a stable
   webhook path and document expected request/response fields next to the
   workflow file.

Current working example for onboarding:

- Open WebUI model id: `prototype_n8n_pipe`
- Open WebUI valve target: `http://n8n:5678/webhook/prototype-postgres-tables`
- Request field: `chatInput`
- Response behavior: summarize table list into a plain assistant reply and
  record continuity in the broker using the returned session/run/event IDs

## Notes

- The compose file uses prototype-safe defaults so it can be rendered without a
  hand-maintained `.env`.
- Do not reuse these defaults for a shared or public deployment.
- Do not commit live Open WebUI passwords, session tokens, or `n8n` API keys
  into the repo. Keep the recovery methods, not the secrets.
- The first continuity-plane artifact is repo-owned SQL under `stack/sql/broker/`.
