# 1215-VPS Roadmap

Ordered phases from [current-state.md](current-state.md) to
[north-star.md](north-star.md). Each phase has a goal, concrete
deliverables, an acceptance check, and a rough effort estimate. Phases run
in order — each assumes the previous ones are complete.

Phase 0 is branch hygiene; Phases A–G define the path to prototype-complete
(v1); Phase H is the operator-facing bringup seam. Deferred items are listed
at the end and are not scheduled here.

## Phase 0 — Stabilize the `proto` Branch (DONE)

Landed in two commits on `proto`:

1. `proto: strip to essentials (formalize trim)` — removed legacy
   architecture docs superseded by the review pack
   (`deployment-model`, `service-catalog`, `network-port-map`,
   `runtime-flows`, `security-observability`, `inter-node-data-flow`,
   `implementation-roadmap`, `learning-plane`, `node-rollout-plan`,
   `prototype-local-shared-core-plan`, `review-01`, `module-env-compilation`,
   `audit/`, `Self-Hosted Long-Horizon Memory Architecture...md`), plus
   `docs/adr/`, `docs/reference/`, `docs/superpowers/`, placeholder
   `nodes/{vps,engineering-pc,local-builder}/` manifests, `.claude/`
   tooling, `CLAUDE.md`, and `bin/start-1215.py`. Phase H rebuilds the
   repo-root shim as `bin/1215`.
2. `proto: phase 0 — stabilize branch (align plan docs with trimmed tree)`
   — rewrote the top-level `README.md` review pack, patched
   `current-state.md` to match the trimmed tree (removed Audit Artifacts
   section, corrected role overlay listing, redirected the
   service-catalog reference to north-star), marked this phase DONE, and
   committed `execution-plan.md` as the executable companion to this
   roadmap.

Kept: `stack/`, `modules/`, and six authoritative architecture documents
— `north-star.md`, `current-state.md`, `roadmap.md`, `execution-plan.md`,
`node-roles.md`, and `overview.md` (legacy reference, deprecation banner
retained).

Acceptance (verified at the Phase 0 commit): `git status --short` shows
no unintended `D` or `??` entries on `proto`; the top-level `README.md`
references only present documents; `current-state.md` accurately
describes the trimmed tree.

A fresh agent session starts at **Phase A** below and uses
`docs/architecture/execution-plan.md` as the concrete per-phase runbook.

## Phase A — Tidy Foundations (~1 day)

Close small drift items before the main work begins.

Deliverables:

- Pin the five unpinned images in
  [stack/prototype-local/docker-compose.substrate.yml](../../stack/prototype-local/docker-compose.substrate.yml):
  `minio/minio`, `minio/mc`, `qdrant/qdrant`, `neo4j:latest`,
  `clickhouse/clickhouse-server`. Use digest pins (`@sha256:...`) consistent
  with the Open WebUI and ComfyUI pattern already in the file.
- Delete the empty `services: {}` overlay at
  [stack/roles/builder/docker-compose.role.yml](../../stack/roles/builder/docker-compose.role.yml)
  (or populate with a real builder service).
- Create a minimal `nodes/linux-prototype/` manifest (`README.md` +
  `roles.env.example` with `core,media-cpu,tools`) so this machine has a
  canonical name in the topology.

Acceptance check: `docker compose -f stack/prototype-local/docker-compose.substrate.yml config`
resolves to fully-pinned images; `nodes/linux-prototype/README.md` and
`nodes/linux-prototype/roles.env.example` both exist.

Candidate for collapse: none — keep as a quick warmup phase.

## Phase B — Host-Native Honcho (~1–2 days)

Bring Honcho under proper host management, share the substrate Postgres, and
retire the separate `1215-honcho-pg` container.

Deliverables:

- Create `stack/services/honcho/` with:
  - `honcho.service` — systemd `--user` unit definition for the FastAPI
  - `honcho-deriver.service` — systemd `--user` unit for the deriver worker
  - `install.sh` — idempotent installer that copies units to
    `~/.config/systemd/user/` and enables them
- Extend `postgres-bootstrap` in
  [docker-compose.substrate.yml](../../stack/prototype-local/docker-compose.substrate.yml)
  to also create a `honcho` database alongside `langfuse`, and enable the
  `pgvector` extension on it.
- Add Honcho env vars to
  [stack/prototype-local/.env.example](../../stack/prototype-local/.env.example):
  `HONCHO_DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5433/honcho`,
  plus `HONCHO_LLM_*` vars per
  [modules/honcho/.env.template](../../modules/honcho/.env.template).
- Update `stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`
  (or supersede with a new `setup_honcho.py`) to stop launching
  `1215-honcho-pg` and instead point Honcho at `127.0.0.1:5433`.
- Expose Honcho at `http://127.0.0.1:18000` (unchanged port; just relocated
  under systemd).

Acceptance check: `systemctl --user status honcho honcho-deriver` both
`active (running)`; `curl http://127.0.0.1:18000/health` returns 200;
a Hermes memory write/read smoke test (extracted from the existing script)
succeeds against the shared Postgres.

Candidate for collapse: can merge with Phase C if you'd rather cut one
phase boundary.

## Phase C — Hermes `orchestrator-ceo` Profile (~1 day)

Stand up the Hermes profile that will back the CEO company.

Deliverables:

- Create `/var/lib/hermes/orchestrator-ceo/` with correct ownership
  (non-root user, group readable by gateway group). Document the install
  via `stack/services/hermes-gateway/scripts/setup_ceo_profile.sh`.
- Create `/var/lib/paperclip/workspaces/orchestrator-ceo/` as the `cwd`.
- Populate the profile `.hermes/` subtree with:
  - `config.toml` pointing at Honcho at `http://127.0.0.1:18000`
  - `skills/` (empty, populated in Phase F)
  - `.env` (host secret file, read at spawn time only)
- Add a **fake-secret canary** — a known fake API key in the env that a
  later test will grep for in Hermes logs / traces. If it ever appears, the
  secret-handling posture has regressed.
- Document the profile layout in a short `README.md` inside the profile
  directory (host-only, not in git).

Acceptance check: `hermes chat --profile orchestrator-ceo --dry-run`
resolves the profile, loads Honcho provider, and exits cleanly; canary
string does not appear in any Hermes-produced file.

Candidate for collapse: small and well-bounded. Keep.

## Phase D — `hermes-gateway` Daemon (~3–5 days, load-bearing)

The only non-trivial new code in this roadmap. This is the container-to-host
boundary that makes Paperclip-in-container + Hermes-on-host safe.

Deliverables:

- New directory [stack/services/hermes-gateway/](../../stack/services/) with:
  - `pyproject.toml` (managed via `uv`, Python >= 3.11)
  - `hermes_gateway/app.py` — FastAPI app bound to a UDS at
    `/run/hermes-gateway/gateway.sock` (mode `0660`, group `hermes-gateway`)
  - Endpoints: `POST /runs/start` (`StartRun`), `POST /runs/{run_id}/attach`
    (`AttachRun` via SSE), `POST /runs/{run_id}/cancel` (`CancelRun`)
  - `hermes_gateway/spawn.py` — wraps `subprocess.Popen` with:
    - **Profile allowlist** (initially: `["orchestrator-ceo"]`) enforced
      before spawn
    - Fixed `PATH`, no shell expansion
    - Per-run working directory from a workspace allowlist
    - Env resolved from host secret files; never reads env from the request
  - `hermes_gateway/broker.py` — publishes `run.created`, `run.started`,
    `run.completed`, `run.failed` to the broker at `http://127.0.0.1:8090`
    with `run_id` idempotency keys
  - `hermes-gateway.service` — systemd `--user` unit
  - `install.sh` — idempotent installer
  - `tests/` — unit tests for the allowlist and spawn-argument construction
- Extend broker event types if needed (check:
  [001_core.sql](../../stack/sql/broker/001_core.sql) already seeds
  `run.created/started/completed/failed` — no migration required).

Acceptance check:

1. `curl --unix-socket /run/hermes-gateway/gateway.sock -X POST http://localhost/runs/start -d '{"profile":"orchestrator-ceo","session_id":"...","prompt":"echo hi"}'`
   returns a `run_id` and a `run.created` event lands in the broker.
2. Attempting to start a run with `"profile":"other"` returns 403 without
   spawning a subprocess.
3. Run completion publishes `run.completed` with matching `run_id`.

Candidate for collapse: none. This is the phase that earns its own name.

## Phase E — Paperclip Container (~2 days)

Fold Paperclip into the compose stack as the single container that reaches
the gateway.

Deliverables:

- Add a `paperclip` service to
  [docker-compose.substrate.yml](../../stack/prototype-local/docker-compose.substrate.yml):
  - Image: built from the `modules/paperclip` submodule (mirror the pattern
    used by the existing host-side docker build in
    `setup_hermes_honcho_paperclip.py`)
  - Port: `127.0.0.1:3100 -> 3100` (match current host-side port)
  - Volume: bind-mount `/run/hermes-gateway` from host (read-write), but
    ONLY for this one container
  - Env: `PAPERCLIP_HERMES_GATEWAY_SOCKET=/run/hermes-gateway/gateway.sock`,
    `PAPERCLIP_BROKER_URL=http://broker:8090`
- Add `paperclip` to the `prototype-local` target in
  [stack/topology/targets.json](../../stack/topology/targets.json).
- Remove the host-side Paperclip launch from
  `stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`
  (Paperclip is now owned by compose).
- Bootstrap an `orchestrator-ceo` Paperclip company (UI + task graph + the
  Hermes profile reference) via a new `stack/prototype-local/scripts/bootstrap_paperclip_ceo.py`.

Acceptance check: `docker compose up -d paperclip`; `curl http://127.0.0.1:3100/api/health`
returns 200; the Paperclip UI shows the `orchestrator-ceo` company; starting
a run from the UI produces a `run.created` event in the broker (via gateway).

Candidate for collapse: can merge with Phase D if you'd rather cut one
phase boundary.

## Phase F — `broadcast_*` and `artifact_*` Hermes Skills (~2 days)

Give Hermes a first-party way to talk to the continuity plane.

Deliverables:

- Populate `/var/lib/hermes/orchestrator-ceo/.hermes/skills/` with:
  - `broadcast_publish.py` — POST `/events` wrapper, idempotency-key aware
  - `broadcast_read_feed.py` — GET `/events` with filters (event type,
    session, run)
  - `broadcast_ack.py` — updates `broker.provider_checkpoints` (requires a
    new broker endpoint; see below)
  - `artifact_publish.py` — MinIO write + POST `/artifacts`
  - `artifact_read.py` — GET `/artifacts` with reference resolution to
    MinIO-signed URL
- Add `POST /checkpoints` and `GET /checkpoints` endpoints to
  [stack/broker/broker_service/app.py](../../stack/broker/broker_service/app.py)
  to support `broadcast_ack`.
- Skill signatures follow the broadcast/artifact API contract implied by
  the broker schema in
  [stack/sql/broker/001_core.sql](../../stack/sql/broker/001_core.sql)
  (events, artifacts, provider_checkpoints tables).

Acceptance check: Hermes running as the CEO can:

1. Publish a `memory.published` event via `broadcast_publish` and see it
   appear in `GET /events`
2. Write an artifact to MinIO via `artifact_publish` and retrieve it via
   `artifact_read`
3. Advance a checkpoint via `broadcast_ack` and read it back

Candidate for collapse: none.

## Phase G — Langfuse Instrumentation (~1–2 days)

Thread correlation IDs through the continuity plane and agent runtime so
traces are useful.

Deliverables:

- In the gateway (Phase D), on `StartRun` generate `run_id` as the
  Langfuse `trace_id` and inject it as env into the Hermes subprocess
  (`LANGFUSE_TRACE_ID`, `LANGFUSE_SESSION_ID`).
- Configure Hermes (either via the profile config or a lightweight wrapper)
  to emit Langfuse spans using the injected trace ID.
- In the broker's event write path
  ([stack/broker/broker_service/app.py](../../stack/broker/broker_service/app.py)),
  attach the `run_id` to `metadata_json.langfuse_trace_id` when present.
- Add a short dashboard or saved view in Langfuse filtering by `trace_id`
  that matches a broker `run_id`.

Acceptance check: Starting a CEO run produces both a Langfuse trace and a
broker `run.created` event sharing the same ID; a multi-step CEO run shows
all spans nested under the one trace.

Candidate for collapse: can be a final polish pass; small enough to stay
as its own phase.

## Phase H — Unified Launch Script (~1 day)

Collapse the existing patchwork (`docker compose` invocations,
`stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`,
ad-hoc `systemctl --user` commands, manual `.env` bootstrapping) into a
single operator entrypoint. This phase is last because it depends on the
artifacts produced in B (Honcho unit), D (gateway unit), and E (Paperclip
compose service) existing.

Deliverables:

- Extend the existing control CLI
  ([stack/control/control1215/cli.py](../../stack/control/control1215/cli.py))
  with five new subcommands. Keep the existing `doctor`, `targets`,
  `services`, `docs` subcommands intact.
  - `up [--target prototype-local]` — idempotent bringup in dependency
    order:
    1. Run `init_env` if `stack/prototype-local/.env` is missing
       (reuses [scripts/init_env.py](../../stack/prototype-local/scripts/init_env.py)).
    2. `docker compose -f stack/prototype-local/docker-compose.substrate.yml up -d`.
    3. Poll Postgres / Valkey / MinIO / ClickHouse `healthz` (timeout
       90s each) before moving on.
    4. `systemctl --user start honcho honcho-deriver` (Phase B artifact).
    5. `systemctl --user start hermes-gateway` (Phase D artifact).
    6. `docker compose up -d paperclip` (Phase E artifact).
    7. Run `gate_shared_core.py` + exposure smoke test + fake-secret
       canary. Fail the command on any gate failure.
  - `down` — reverse order. Stop compose stack, stop user units. Never
    removes volumes; `--volumes` flag required for destructive stop.
  - `status` — single-table view: every service with `state`, `port`,
    and a short `hint` (last-error snippet or "—"). Wraps
    `docker compose ps --format json`, `systemctl --user show`, and
    per-service `/healthz` calls.
  - `logs <service> [--follow]` — routes to `docker compose logs` or
    `journalctl --user -u <service>` based on service type. A
    `service -> source` map lives in
    `stack/control/control1215/lifecycle.py`.
  - `smoke` — runs `gate_shared_core.py`, the exposure smoke test, and
    the fake-secret canary in isolation (no bringup/teardown side
    effects). Exits non-zero on any failure.
- Rename the root shim from `bin/start-1215.py` to `bin/1215` (same
  pattern; `+x`; execvp into `uv run --project stack/control start-1215`).
  Keep a one-line `bin/start-1215.py` symlink or tombstone for one phase
  to avoid breaking muscle memory, then remove in the next commit.
- Retire
  [stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py](../../stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py).
  Its substrate bringup is covered by compose, its Honcho bringup by Phase
  B's systemd unit, its Paperclip bringup by Phase E's compose service.
  Delete the file once `1215 up` has replaced it end-to-end (not earlier —
  it's the only working bringup until all of B/C/D/E land).
- Every subcommand is idempotent: `1215 up` twice is a no-op on the
  second run; `1215 down` on a clean system exits 0 with "nothing to
  stop".
- Every subcommand prints a machine-readable summary on `--json` for CI
  use.

Acceptance check:

1. `./bin/1215 up` on a cold machine reaches "all green" in
   `./bin/1215 status` in under 3 minutes.
2. `./bin/1215 smoke` passes immediately after `1215 up` completes.
3. `./bin/1215 down && ./bin/1215 up` returns to a byte-identical
   `status` output (modulo timestamps).
4. `./bin/1215 status` on a half-up system (e.g. compose up, user units
   stopped) shows exactly which services are missing without crashing
   and with non-zero exit code.
5. `docker compose -f stack/prototype-local/docker-compose.substrate.yml ps`
   and `systemctl --user list-units --state=active` agree with
   `./bin/1215 status` — no drift.

Candidate for collapse: none — this is the operator-facing seam and
earns its own phase. The actual implementation is small because it
wraps existing pieces; the discipline is in idempotency and the
status/logs routing table.

## Cross-Phase Gates

Two tests should run after every phase from C onward and should be added to
`gate_shared_core.py`:

- **Exposure smoke test** — scans running containers for any non-loopback
  host bind. Fails if any `0.0.0.0` bind exists. Runs before each phase's
  acceptance check.
- **Fake-secret canary** — scans recent Hermes logs, Langfuse traces, and
  broker event payloads for the canary string from Phase C. Fails if the
  canary appears anywhere.

## Deferred Items (Not Scheduled)

Explicitly out of this roadmap. Named here so nothing is silently
forgotten.

- **Edge layer**: Caddy, Tailscale, Cloudflared. The prototype stays
  localhost-only until the VPS itself is in play.
- **Learning-plane runtime**: no `learning-orchestrator`, `eval-runner`,
  `dataset-builder`, or `candidate-registry` runtime services. Reference
  modules (`autoreason`, `hermes-agent-self-evolution`) stay as submodules.
- **Cross-node publish / replay**: engineering-pc ↔ VPS ↔ research-host
  flows are out. The broker's outbox/replay-cursor machinery exists in the
  schema but is not exercised.
- **Additional specialist workers** beyond ComfyUI: transcription, batch
  inference, data synthesis. Add via the same pattern when the CEO loop is
  stable.
- **Restart-resilience and backup/restore drills**: scheduled as operational
  work, not architectural work. Worth doing; not in this roadmap.

## Rough Total

- Phase 0: ~½ day (branch hygiene).
- Phases A–G: ~12–17 working days end-to-end, assuming focused work and no
  major snag on Phase D (the gateway). Phase D is the single biggest risk;
  the others are well-shaped.
- Phase H: ~1 day (wraps existing pieces; discipline cost, not code cost).
- **Total: ~14–19 working days** for `proto` → prototype-complete.
- The prototype is **prototype-complete** when all of A–H pass their
  acceptance checks, with every cross-phase gate green.
