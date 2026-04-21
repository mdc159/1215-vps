# 1215-VPS Current State

Factual snapshot of what is actually in this repository as of the time of
writing. No opinions, no aspirations. Sourced directly from
`docker-compose.substrate.yml`, `stack/sql/`, `stack/broker/`,
`stack/topology/`, `stack/roles/`, `nodes/`, and
`stack/prototype-local/scripts/`.

For the target state, see [north-star.md](north-star.md). For the plan to
close the gap, see [roadmap.md](roadmap.md).

## Services Actually Running

All services defined in
[stack/prototype-local/docker-compose.substrate.yml](../../stack/prototype-local/docker-compose.substrate.yml).
Every host port is bound to `127.0.0.1` only — no `0.0.0.0` binds exist.

| Service | Image | Host binds | Internal DNS | Volumes |
|---|---|---|---|---|
| `broker` | Built from `stack/broker` (Python + FastAPI + psycopg) | `127.0.0.1:8090 -> 8090` | `broker:8090` | none |
| `postgres` | `postgres:17` | `127.0.0.1:5433 -> 5432` | `postgres:5432` | `prototype_postgres_data` |
| `postgres-bootstrap` | `postgres:17` (one-shot) | — | — | — |
| `valkey` | `docker.io/valkey/valkey:8-alpine` | `127.0.0.1:6379 -> 6379` | `valkey:6379` | `prototype_valkey_data` |
| `minio` | `minio/minio` (unpinned) | `127.0.0.1:9010 -> 9000`, `127.0.0.1:9011 -> 9001` | `minio:9000` | `prototype_minio_data` |
| `minio-init` | `minio/mc` (unpinned) (one-shot) | — | — | — |
| `shared-data-init` | `busybox:1.36` (one-shot) | — | — | `prototype_shared_data` |
| `qdrant` | `qdrant/qdrant` (unpinned) | `127.0.0.1:6333 -> 6333`, `127.0.0.1:6334 -> 6334` | `qdrant:6333` | `prototype_qdrant_data` |
| `neo4j` | `neo4j:latest` (unpinned) | `127.0.0.1:7474 -> 7474`, `127.0.0.1:7473 -> 7473`, `127.0.0.1:7687 -> 7687` | `neo4j:7687` | `prototype_neo4j_{data,logs,config,plugins}` |
| `clickhouse` | `clickhouse/clickhouse-server` (unpinned) | `127.0.0.1:8123 -> 8123`, `127.0.0.1:9000 -> 9000`, `127.0.0.1:9009 -> 9009` | `clickhouse:8123/9000` | `prototype_clickhouse_{data,logs}` |
| `langfuse-worker` | `langfuse/langfuse-worker:3` | `127.0.0.1:3030 -> 3030` | `langfuse-worker:3030` | — |
| `langfuse-web` | `langfuse/langfuse:3` | `127.0.0.1:3000 -> 3000` | `langfuse-web:3000` | — |
| `open-webui` | `ghcr.io/open-webui/open-webui@sha256:000b87a6…` | `127.0.0.1:8080 -> 8080` | `open-webui:8080` | `prototype_open_webui_data` |
| `comfyui` | `ghcr.io/lecode-official/comfyui-docker@sha256:e27739fc…` | `127.0.0.1:8188 -> 8188` | `comfyui:8188` | `prototype_comfyui_{models,custom_nodes,output}`, `prototype_shared_data` |
| `n8n` | Built from `stack/prototype-local/n8n` (base `n8nio/n8n:2.3.6`) | `127.0.0.1:5678 -> 5678` | `n8n:5678` | `prototype_n8n_data`, `prototype_shared_data` |
| `n8n-mcp` | `ghcr.io/czlonkowski/n8n-mcp:2.33.5` | `127.0.0.1:13000 -> 3000` | `n8n-mcp:3000` | `prototype_n8n_mcp_data` |

14 long-running services plus 3 one-shot init containers
(`postgres-bootstrap`, `minio-init`, `shared-data-init`). Five images are
unpinned (`minio/minio`, `minio/mc`, `qdrant/qdrant`, `neo4j:latest`,
`clickhouse/clickhouse-server`).

The Langfuse stack uses:

- Postgres (shared, database `langfuse` created by `postgres-bootstrap`)
- ClickHouse (primary analytics store)
- MinIO (bucket `langfuse` for events + media uploads, prefix-segmented)
- Valkey (Redis-compatible cache)

ComfyUI runs in CPU mode (`--cpu`) with CORS headers enabled and a shared
`/data/shared` mount that the n8n container also sees.

## Host-Side Assets

`stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py` — a
manual one-shot bringup script that:

- installs `hermes-agent` from the repo submodule and runs it on the host
- stands up a **separate** `1215-honcho-pg` Postgres container (distinct from
  the substrate `postgres`) and bind-runs Honcho's FastAPI + deriver on the
  host, reachable at `http://127.0.0.1:18000`
- builds and runs the Paperclip docker image (also separately, not via
  `docker-compose.substrate.yml`), reachable at `http://127.0.0.1:3100`
- runs a Hermes → Honcho memory smoke test

No systemd units exist anywhere in the repo. Every host-side process is
manually managed via this script.

Other scripts in `stack/prototype-local/scripts/`:

- `init_env.py` — seeds `.env` from `.env.example`
- `bootstrap_n8n.py` — provisions n8n API keys and imports workflow JSON
- `sync_openwebui_functions.py` — installs Open WebUI pipe functions
- `test_openwebui_n8n_broker.py` — E2E test of the OWU → n8n → broker flow
- `test_n8n_mcp_functional.py` — functional test of n8n-mcp tools
- `gate_shared_core.py` — prototype-local shared-core gate runner

## Broker Schema

[stack/sql/broker/001_core.sql](../../stack/sql/broker/001_core.sql) defines
a single `broker` schema with 9 tables.

**Lookup tables** (seeded at migration time):

- `broker.event_types` — 12 event types seeded: `node.upserted`,
  `session.created`, `run.created`, `run.started`, `run.completed`,
  `run.failed`, `workflow.started`, `workflow.completed`, `workflow.failed`,
  `artifact.registered`, `memory.published`, `memory.recalled`
- `broker.artifact_kinds` — 5: `document`, `trace-export`, `workflow-output`,
  `memory-extract`, `blob`
- `broker.checkpoint_kinds` — 3: `publish-outbox`, `replay-cursor`,
  `provider-sync`

**Entity tables:**

- `broker.nodes` — node registry (`node_id`, `node_role`, `display_name`,
  `metadata_json`)
- `broker.sessions` — continuity sessions bound to a node and surface
- `broker.runs` — run lifecycle (`run_id`, `session_id`, `run_kind`,
  `status`, timestamps)
- `broker.events` — canonical append-only event log with `event_seq`
  (identity), `event_id` (unique), `payload_version`, `idempotency_key`
  (unique per node), `source_event_id` + `source_event_hash` for lineage,
  `occurred_at`, `recorded_at`, `payload_json`, `metadata_json`.
  Payload and metadata both constrained to JSONB objects.
- `broker.artifacts` — artifact manifests keyed by `(storage_backend, uri)`,
  linked to `source_event_id` + `source_event_hash`
- `broker.provider_checkpoints` — consumer offsets keyed by
  `(provider_name, node_id, checkpoint_kind)`

Indexes exist on `events.event_type`, `events.session_id`, `events.run_id`,
and `artifacts.source_event_id`.

## Broker API Surface

[stack/broker/broker_service/app.py](../../stack/broker/broker_service/app.py)
exposes a FastAPI application at `:8090` with the following endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | DB connectivity + service name |
| POST | `/nodes` | Upsert a node registration |
| POST | `/sessions` | Create or update a session |
| POST | `/runs` | Create or update a run |
| POST | `/events` | Append an event, idempotent per `(node_id, idempotency_key)` |
| GET | `/events` | List most recent events (limit 1–500, default 50) |
| POST | `/artifacts` | Upsert an artifact manifest by `(storage_backend, uri)` |
| GET | `/artifacts` | List artifacts, optionally filtered by `source_event_id` |
| GET | `/config` | Database / service introspection |

Request models are defined as Pydantic `BaseModel` classes
(`NodeUpsert`, `SessionCreate`, `RunCreate`, `EventCreate`, `ArtifactCreate`).
Configuration comes from environment variables (`BROKER_DATABASE_*`,
`BROKER_SERVICE_NAME`).

## Topology Declarations

[stack/topology/services.json](../../stack/topology/services.json) enumerates
services with `layer`, `role`, and `exposure` metadata. Covers: `open-webui`,
`paperclip`, `n8n`, `comfyui`, `n8n-mcp`, and the substrate set.

[stack/topology/targets.json](../../stack/topology/targets.json) defines two
targets:

- `prototype-local` — `compose_files: ["stack/prototype-local/docker-compose.substrate.yml"]`;
  services list includes the 12 runtime containers **plus** `comfyui`, but
  does **not** include `paperclip`, `honcho`, `hermes-gateway`, or `hermes`.
- `vps-hub` — `compose_files: []` (empty). Services array lists 15 items
  including `paperclip`, `honcho`, `hermes-gateway`, `hermes`. This target
  has no compose wiring — it is a declaration only, not yet a runnable
  configuration.

[stack/topology/roles.json](../../stack/topology/roles.json) defines roles:
`core`, `vps`, `media-cpu`, `media-gpu`, `builder`, `tools`. See next
section for their compose-file state.

## Role Overlays

Directory state under [stack/roles/](../../stack/roles/):

- `core/` — empty directory, no compose file
- `vps/` — empty directory, no compose file
- `builder/docker-compose.role.yml` — present, content is `services: {}`
- `media-cpu/docker-compose.role.yml` — present
- `media-gpu/docker-compose.role.yml` — present
- `tools/docker-compose.role.yml` — present

The role overlay system is scaffolded but only partially populated.

## Node Manifests

[nodes/](../../nodes/) contains three placeholder directories:

- `nodes/vps/` — `README.md`, `roles.env.example` (role string:
  `core,vps,media-cpu,tools`)
- `nodes/engineering-pc/` — `README.md`, `roles.env.example` (role string:
  `core,media-gpu,tools`)
- `nodes/local-builder/` — `README.md`, `roles.env.example` (role string:
  `core,builder,tools`)

All files are `.example`s. No live `roles.env` file for any node. This
machine (the Linux prototype) does not yet have a node manifest directory.

## Environment Configuration

[stack/prototype-local/.env.example](../../stack/prototype-local/.env.example)
is the template for local configuration. The live
`stack/prototype-local/.env` is `.gitignore`-excluded and contains
placeholders for Postgres, MinIO, Langfuse, n8n, Neo4j, Honcho, Broker,
Paperclip credentials. Module-specific `.env.example` / `.env.template`
files exist under `modules/*/`.

No committed secrets exist in the repo (verified via `.gitignore` coverage
of `stack/prototype-local/.env`).

## Audit Artifacts

[docs/architecture/audit/](audit/) contains:

- `drift-matrix.md` — claim → evidence → status matrix across all 14
  repo-owned architecture docs
- `claims-index.json` — machine-readable list of claims and statuses
- `README.md` — narrative summary of top findings

These are historical outputs of an audit run; this current-state document
distils the factual parts but does not re-analyze drift.

## What Is Decidedly Not In The Repo

Explicit list of things referenced by `north-star.md` but absent today:

- **`stack/services/hermes-gateway/`** — no directory, no daemon code, no
  systemd unit, no Unix domain socket contract. The "host-only Hermes
  gateway" is documented in `service-catalog.md` but not implemented.
- **`orchestrator-ceo` Hermes profile** — no `HERMES_HOME` layout, no
  profile config, no skills directory. The `setup_hermes_honcho_paperclip.py`
  smoke test runs Hermes against a default profile only.
- **Paperclip container entry** — not in `docker-compose.substrate.yml`.
  Paperclip is installed and run from the host script, not the compose
  stack, and is not part of any documented compose target.
- **Honcho as a managed service** — runs from the host via the setup script,
  against its own isolated `1215-honcho-pg` Postgres container. No systemd
  unit, no compose service, and not wired to the shared substrate Postgres.
- **Edge layer** — no Caddy config, no Tailscale config, no Cloudflared
  config, no `caddy`/`tailscale`/`cloudflared` services anywhere in the
  repo. Everything is localhost-only.
- **Learning-plane runtime** — `autoreason` and `hermes-agent-self-evolution`
  are present as submodules (declared in `.gitmodules`). No
  `learning-orchestrator`, `eval-runner`, `dataset-builder`, or
  `candidate-registry` runtime services exist.
- **`broadcast_*` / `artifact_*` Hermes skills** — no skills on any profile
  that wrap the broker API as callable Hermes skills. The broker API is
  reachable but no agent currently calls it as a skill.
- **Langfuse correlation wiring** — Langfuse is running, but there is no
  code that threads `run_id` from broker events to Langfuse `trace_id`, and
  no Hermes spans are emitted.
- **`vps-hub` compose implementation** — the target is declared with 15
  services but `compose_files` is empty.
- **Node manifest for this machine** — no live `nodes/<this-host>/` entry
  describing what the Linux prototype is playing.
