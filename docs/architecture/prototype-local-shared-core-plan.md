# Prototype-Local Shared-Core Plan

## Purpose

This document turns the current repo state into a concrete implementation plan
for the Linux prototype node.

The target is a single-device prototype that proves the minimum shared-core
slice common to the future VPS hub and local nodes:

- Open WebUI -> `n8n` -> ComfyUI
- Paperclip -> Hermes via gateway only
- Hermes -> Honcho memory
- `n8n-mcp` running against the same local `n8n`
- broker continuity and artifact lineage
- basic functional, canary, and restart testing

This plan is based on the codebase as it exists now, not just on architecture
intent.

## Current Baseline

### Already implemented

- Local substrate compose in [stack/prototype-local/docker-compose.substrate.yml](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/docker-compose.substrate.yml)
- Broker API and schema in:
  - [stack/broker/broker_service/app.py](/mnt/data/Documents/repos/1215-vps/stack/broker/broker_service/app.py)
  - [stack/sql/broker/001_core.sql](/mnt/data/Documents/repos/1215-vps/stack/sql/broker/001_core.sql)
- Repo-owned Open WebUI pipes in [stack/prototype-local/open-webui/functions](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/open-webui/functions)
- Repo-owned `n8n` workflow JSON in [stack/prototype-local/n8n](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/n8n)
- `n8n-mcp` service definition in the local substrate compose
- Node/role selection tooling in:
  - [bin/start-1215.py](/mnt/data/Documents/repos/1215-vps/bin/start-1215.py)
  - [stack/control/control1215](/mnt/data/Documents/repos/1215-vps/stack/control/control1215)

### Verified on this Linux machine

- `stack/control` tests pass
- `stack/broker` tests pass
- Broker health works on `:8090`
- `n8n` Postgres-table webhook works and records continuity rows in the broker
- MinIO bucket webhook works
- ComfyUI stats webhook works
- ComfyUI SD1.5 queue webhook works
- Open WebUI has the repo-owned pipe models imported into its local database
- `n8n-mcp` is running locally and healthy

### Not yet implemented as repo-owned runtime

- Honcho service wiring under `stack/`
- Hermes gateway daemon and shim under `stack/`
- Paperclip-orchestrator image/service under `stack/`
- Broker artifact registration from the media workflows
- Authenticated Open WebUI end-to-end test harness
- Shared-core gate tests for memory, fake-secret canary, and restart resilience

## Critical Gaps

### Gap 1: repo metadata is ahead of runnable reality

[stack/topology/targets.json](/mnt/data/Documents/repos/1215-vps/stack/topology/targets.json)
claims `prototype-local` includes:

- `paperclip`
- `honcho`
- `hermes-gateway`
- `hermes`

But those services do not exist in the actual prototype compose file yet.

### Gap 2: substrate is real, shared-core gate is not

The current prototype proves substrate and parts of the continuity path, but it
does not yet prove:

- Paperclip -> Hermes through gateway only
- Honcho-backed memory persistence and recall
- fake-secret canary safety
- restart resilience for the host-execution and memory seams

### Gap 3: media storage exists without full continuity lineage

The current media path can reach MinIO, but the repo-owned media workflows do
not yet register artifacts into `broker.artifacts`. MinIO upload exists; broker
artifact lineage does not.

### Gap 4: `n8n-mcp` exists but is not yet part of the prototype gate

`n8n-mcp` is currently present as a service and healthy locally, but it is
still treated as optional in the local prototype docs and has no functional
verification beyond service health.

### Gap 5: committed local secrets must be cleaned up

[stack/prototype-local/.env](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/.env)
contains live-looking secrets and must not remain committed if this prototype is
going to become the real node baseline.

## Required End State

The Linux prototype should be considered complete only when all of the
following are true:

- Open WebUI -> `n8n` -> broker works through authenticated API calls
- Open WebUI -> `n8n` -> ComfyUI -> MinIO -> broker artifact registration works
- `n8n-mcp` is up, authenticated, and functionally verified against local `n8n`
- Paperclip can invoke Hermes only through the gateway
- Hermes uses Honcho and recalls durable memory across sessions
- fake-secret canary checks pass
- restart resilience passes without manual repair

## Implementation Plan

## Phase 0: Make Repo State Truthful

### Objective

Bring docs, topology metadata, and runtime reality back into sync.

### Tasks

- Reconcile [stack/topology/targets.json](/mnt/data/Documents/repos/1215-vps/stack/topology/targets.json) with the actual `prototype-local` compose stack.
- Update [stack/prototype-local/README.md](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/README.md) so it reflects what is actually implemented and required.
- Decide explicitly that `n8n-mcp` is part of the Linux prototype done bar.
- Add a short "prototype done bar" section to the prototype README and keep it aligned with this document.

### Acceptance criteria

- No service is claimed in topology unless it exists in the actual runtime.
- The README and compose file describe the same prototype scope.
- `./bin/start-1215.py services --target prototype-local` matches live compose reality.

## Phase 1: Clean Secrets and Stabilize the Existing Substrate

### Objective

Make the current local substrate safe and reproducible before deepening it.

### Tasks

- Remove [stack/prototype-local/.env](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/.env) from version control and rotate all contained secrets.
- Keep only [stack/prototype-local/.env.example](/mnt/data/Documents/repos/1215-vps/stack/prototype-local/.env.example) committed.
- Pin image versions for:
  - Open WebUI
  - `n8n`
  - `n8n-mcp`
  - ComfyUI
- Add repo-owned bootstrap steps for:
  - broker schema apply
  - `n8n` workflow import/activation
  - Open WebUI function import/update
- Ensure all intended local webhooks are registered deterministically after fresh bring-up.
- Decide whether Python task runner support is required in `n8n`; if yes, build it into the custom image.

### Acceptance criteria

- Fresh `compose up` on a clean volume set yields the expected services and active workflows.
- All declared local webhook paths respond correctly after restart.
- No live secrets remain committed in the repo.

## Phase 2: Complete the Current Open WebUI -> n8n -> Broker Path

### Objective

Turn the existing chat ingress into a reproducible, tested continuity path.

### Tasks

- Add authenticated Open WebUI bootstrap and API smoke steps to the repo docs/scripts.
- Add a reproducible test that:
  - authenticates to Open WebUI
  - calls `/api/chat/completions` using `prototype_n8n_pipe`
  - verifies broker node/session/run/event creation
- Ensure continuity IDs are easy to inspect after each run.
- Confirm the current workflow import path always activates the Open WebUI-facing webhook.

### Acceptance criteria

- A test run through Open WebUI chat creates broker continuity rows every time.
- The system can prove the path from user-facing shell to workflow engine to continuity plane.

## Phase 3: Complete the Media Path with Artifact Lineage

### Objective

Make the current ComfyUI media path satisfy the continuity contract, not just
the storage path.

### Tasks

- Extend the broker API if needed to support artifact registration as a first-class write path.
- Update the ComfyUI artifact workflow to:
  - create or update broker run status
  - emit `workflow.completed`
  - register an artifact row in `broker.artifacts`
  - emit `artifact.registered`
- Include durable metadata:
  - object key
  - MIME type
  - checksum
  - source event linkage
  - source workflow/run linkage
- Return broker continuity IDs in the workflow response alongside the MinIO URL.

### Acceptance criteria

- A successful media generation produces:
  - a ComfyUI output
  - a MinIO object
  - a broker run row
  - a broker event row
  - a broker artifact row
- `broker.artifacts` is non-empty after a successful generation.

## Phase 4: Promote n8n-mcp to a Required Prototype Component

### Objective

Treat `n8n-mcp` as part of the prototype control and inspection surface, not as
an optional extra.

### Tasks

- Move `n8n-mcp` from "optional" to "required for prototype-local" in docs and bring-up conventions.
- Pin the `n8n-mcp` image version.
- Add bootstrap verification for:
  - `/health`
  - auth token
  - local `n8n` API connectivity
- Add functional tests that prove `n8n-mcp` can:
  - discover the live runtime node catalog
  - inspect imported workflows
  - fetch workflow structure and node metadata
  - distinguish missing runtime nodes from valid ones
- Add one safe management test:
  - create, clone, or update a disposable workflow via `n8n-mcp`
  - verify it appears in local `n8n`
  - optionally deactivate or delete it afterward
- Add one negative test proving `n8n-mcp` does not itself repair missing runtime nodes.

### Acceptance criteria

- `n8n-mcp` is part of standard bring-up for the Linux prototype.
- Functional tests prove it can inspect and manage the local `n8n` instance.
- `n8n-mcp` is included in the shared-core prototype gate.

## Phase 5: Add Honcho as a Real Prototype Service

### Objective

Stand up Honcho privately on this Linux machine with deterministic env and DB
configuration.

### Tasks

- Implement repo-owned Honcho compose wiring under `stack/`, not just notes in [docs/honcho.md](/mnt/data/Documents/repos/1215-vps/docs/honcho.md).
- Add DB init for:
  - `honcho` database
  - `honcho_app` role
  - required extensions
- Render `HONCHO_DB_CONNECTION_URI` deterministically from env.
- Decide the local derivation/embedding model configuration for the prototype.
- Keep Honcho private:
  - Docker-internal only or localhost only
  - no public route
- Add health and readiness checks.

### Acceptance criteria

- Honcho boots through repo-owned configuration.
- Honcho health works.
- Hermes can target Honcho through a stable local base URL.
- Honcho is not publicly exposed.

## Phase 6: Implement the Hermes Gateway

### Objective

Create the real host-execution boundary required by the architecture.

### Tasks

- Add a repo-owned gateway implementation under `stack/services/hermes-gateway/` or equivalent.
- Add a systemd unit and install path for this Linux host.
- Add a container shim named `hermes` that forwards to `/run/hermes-gateway/hermes.sock`.
- Enforce gateway policy:
  - authoritative `HERMES_HOME` from `--profile`
  - `cwd` constrained to allowed workspace roots
  - protected env stripping
  - per-profile serialization
- Add a lightweight echo/help round-trip for testability.

### Acceptance criteria

- From inside a test container, `hermes --profile orchestrator-ceo --help` reaches the host Hermes binary through the socket.
- Malicious `HERMES_HOME` overrides are ignored.
- Same-profile requests serialize; different-profile requests can run concurrently.

## Phase 7: Add Paperclip-Orchestrator

### Objective

Run Paperclip against Hermes only through the gateway and adapter semantics.

### Tasks

- Build a repo-owned `paperclip-orchestrator` image that layers the Hermes shim onto Paperclip.
- Bind-mount:
  - gateway socket
  - allowed workspace root
- Wire Paperclip to the existing adapter semantics from [modules/hermes-paperclip-adapter/src/server/execute.ts](/mnt/data/Documents/repos/1215-vps/modules/hermes-paperclip-adapter/src/server/execute.ts)
- Preserve:
  - `persistSession`
  - `--resume`
  - `--profile`
  - `cwd`
  - merged `env`
  - `--yolo`
- Start with one orchestrator profile only for this Linux prototype.
- Add a basic Paperclip smoke path that invokes Hermes through the adapter.

### Acceptance criteria

- Paperclip reaches Hermes only through the gateway socket and shim.
- No direct host-binary bypass exists in container wiring.
- A Paperclip-triggered Hermes run succeeds and is inspectable.

## Phase 8: Connect Hermes to Honcho

### Objective

Prove durable memory works through the intended Hermes -> Honcho path.

### Tasks

- Create the real Hermes profile/workspace layout for this Linux prototype.
- Configure Hermes to use Honcho as its external memory provider.
- Add scripted memory tests:
  - write a harmless fact
  - start a fresh session
  - verify recall
- Add status and doctor checks for both Hermes and Honcho.
- Add a fake-secret canary test through the same path.

### Acceptance criteria

- Cross-session recall works through Honcho.
- Fake-secret canary does not persist in:
  - Honcho memory
  - broker rows
  - Langfuse
  - repo files
  - service logs

## Phase 9: Add End-to-End Prototype Test Harness

### Objective

Make the Linux prototype reproducible and gateable.

### Tasks

- Add a repo-owned test harness under the prototype stack for end-to-end verification.
- Include at minimum these tests:

1. `substrate_up`
   - compose up
   - broker, Open WebUI, `n8n`, `n8n-mcp`, MinIO, ComfyUI, and later Honcho health

2. `broker_schema`
   - broker SQL applied
   - expected broker tables exist

3. `n8n_webhooks`
   - expected local webhook paths respond

4. `openwebui_n8n_broker`
   - authenticated Open WebUI call using `prototype_n8n_pipe`
   - broker node/session/run/event assertions

5. `openwebui_n8n_comfyui_minio_broker`
   - authenticated Open WebUI or direct webhook call using the ComfyUI path
   - MinIO object assertion
   - broker artifact assertion

6. `n8n_mcp_functional`
   - health
   - auth
   - node discovery
   - workflow inspection
   - disposable workflow management test

7. `paperclip_gateway_roundtrip`
   - `hermes --profile ... --help` from inside Paperclip container

8. `honcho_memory`
   - harmless fact write and fresh-session recall

9. `fake_secret_canary`
   - inject canary
   - verify absence from memory, broker, traces, logs, and repo files

10. `restart_resilience`
   - restart stack
   - rerun critical checks without manual repair

### Acceptance criteria

- One command can run the shared-core prototype gate.
- Failures are attributed clearly to a specific subsystem.

## Phase 10: Promote This Box to a Real Prototype Node

### Objective

Stop relying on example manifests and make this Linux machine the actual
prototype node definition.

### Tasks

- Create a real node manifest for this machine under `nodes/`.
- Likely enabled roles:
  - `core`
  - `vps`
  - `media-cpu`
  - `tools`
- Update bring-up instructions to use the real node manifest rather than example-only manifests.
- Ensure `start-1215` workflows operate through the real node manifest.

### Acceptance criteria

- `./bin/start-1215.py show-node <real-node>` describes the actual prototype.
- Bring-up and test commands run through repo-owned node selection, not ad hoc compose usage.

## Recommended Execution Order

1. Make repo state truthful
2. Clean secrets and stabilize substrate
3. Complete broker artifact registration
4. Make `n8n-mcp` required and tested
5. Add Honcho
6. Add Hermes gateway
7. Add Paperclip-orchestrator
8. Wire Hermes to Honcho
9. Add end-to-end harness
10. Add canary and restart tests
11. Promote this box to a real node manifest

## Prototype Done Bar

The Linux prototype is complete only when all of the following are true:

- Open WebUI -> `n8n` -> broker works through authenticated API
- Open WebUI -> `n8n` -> ComfyUI -> MinIO -> broker artifact registration works
- `n8n-mcp` is up, authenticated, and functionally verified against local `n8n`
- Paperclip can invoke Hermes only through the gateway
- Hermes uses Honcho and recalls durable memory across sessions
- fake-secret canary passes
- restart resilience passes once without manual repair

## Suggested Task Groups

- `prototype-foundation`
- `prototype-media-lineage`
- `prototype-n8n-mcp`
- `prototype-honcho`
- `prototype-hermes-gateway`
- `prototype-paperclip`
- `prototype-e2e-tests`
- `prototype-restart-and-canary`

## Notes

- This plan is intentionally implementation-oriented. It describes what must be
  added to this repo and this machine to reach the prototype target.
- `n8n-mcp` is included as a first-class prototype component.
- The current substrate is real and useful, but it is not yet the full
  shared-core prototype described in the architecture and rollout documents.
