# 1215-VPS Execution Plan: `proto` → North Star

Self-contained executable plan for a fresh agent session. Pair this with
[roadmap.md](roadmap.md) (architectural intent per phase),
[north-star.md](north-star.md) (target state), and
[current-state.md](current-state.md) (baseline snapshot).

**Primary discipline**: one phase → one verified acceptance check → one commit.
No merging phases, no batch commits, no commits on failed acceptance.

---

## Handoff State — Read This First

If you are a fresh agent opening this plan, this is the ground truth:

- **Branch**: `proto`.
- **Phase 0 is DONE**. Your starting todo is **Phase A**.
- **Top two commits on `proto`**:
  1. `proto: strip to essentials (formalize trim)` — legacy docs, placeholder
     node manifests, `.claude/` tooling, `CLAUDE.md`, and `bin/start-1215.py`
     have been removed.
  2. `proto: phase 0 — stabilize branch (align plan docs with trimmed tree)`
     — top-level `README.md`, `current-state.md`, `roadmap.md`, and this
     `execution-plan.md` all reflect the trimmed tree.
- **`bin/` is currently empty**. Phase H rebuilds `bin/1215`. Do not try
  `./bin/start-1215.py` — it no longer exists. Use
  `uv run --project stack/control start-1215 <subcommand>` until Phase H.
- **Authoritative architecture docs** (all that remain under
  `docs/architecture/`): `north-star.md`, `current-state.md`, `roadmap.md`,
  `execution-plan.md` (this file), `node-roles.md`, and `overview.md`
  (legacy reference, deprecation banner retained).
- **Working tree may show**:
  - A dirty `claude-memory-compiler` submodule — ignore; it's a reference
    submodule and not wired into the runtime.
  - A local `stack/prototype-local/.env` — gitignored; never commit it.
  Anything else in `git status --short` is unexpected. Investigate before
  touching code.
- **Stack state**: the substrate containers were last brought up and are
  expected to be either running or cleanly stoppable via
  `docker compose -f stack/prototype-local/docker-compose.substrate.yml down`.
  Honcho, the Hermes gateway, and the Paperclip container are **not** yet
  assembled — they are the Phase B / D / E deliverables.

---

## Context You Must Load First

Before touching anything, read these in this order:

1. `docs/architecture/north-star.md` — the target architecture.
2. `docs/architecture/current-state.md` — the factual baseline.
3. `docs/architecture/roadmap.md` — detailed deliverables and acceptance
   criteria for every phase. **This file (execution-plan.md) intentionally
   does not duplicate the architectural spec**; read the matching
   `## Phase X` section in `roadmap.md` for each phase before starting it.

## Session Kickoff (Run Once at the Start of a Fresh Session)

1. Read the three context documents listed above.
2. Confirm the Handoff State is still true:
   ```bash
   cd /home/hammer/Documents/repos/1215-vps
   git branch --show-current         # must print: proto
   git log --oneline -3              # top two commits match Handoff State
   git status --short                # only the ignorable items listed above
   ```
3. Recreate the top-level TODO list with these exact eight items
   (TodoWrite state does not persist across sessions):
   - `phase_a` — Tidy foundations
   - `phase_b` — Host-native Honcho
   - `phase_c` — Hermes orchestrator-ceo profile
   - `phase_d` — hermes-gateway daemon
   - `phase_e` — Paperclip container
   - `phase_f` — broadcast_* and artifact_* Hermes skills
   - `phase_g` — Langfuse instrumentation
   - `phase_h` — Unified launch script
4. Run the pre-flight checks below.
5. Work through phases in order. For each phase:
   - Mark its top-level TODO `in_progress` **before** reading its
     `roadmap.md` section.
   - Read the matching `## Phase X` section in `roadmap.md` for full
     deliverable detail.
   - **Create sub-todos** for that phase's deliverables as you identify
     them (naming pattern: `phase_<x>.<n> <short-label>`). Do this in
     the same turn you mark the phase `in_progress`.
   - Execute the deliverables one at a time. After each logical chunk:
     land a WIP commit per `## Commit Cadence`, then mark that sub-todo
     `completed` in the same turn.
   - When all sub-todos are `completed`, run the phase's acceptance
     check from this document.
   - On pass: land the phase-closing commit, `git push origin proto`,
     then mark the top-level phase TODO `completed`.
   - On fail: diagnose, fix, re-run. Do not land the phase-closing
     commit. Do not advance. WIP commits already in the chain stay.
6. Stop and report when any of these is true:
   - All eight phases are `completed`.
   - An invariant would be violated by the next required action.
   - Two focused attempts on the same phase's acceptance check have
     failed.
   - The user interrupts.

## Pre-flight (Run Once at Session Start)

```bash
cd /home/hammer/Documents/repos/1215-vps
git branch --show-current                               # must print: proto
git status --short                                      # only ignorable items
docker ps                                               # must succeed
systemctl --user status                                 # must succeed
uv --version                                            # must succeed

# Sanity-check the control CLI (no bin/start-1215.py exists until Phase H):
uv run --project stack/control start-1215 doctor        # exits 0
```

If any of these fail for infrastructure reasons (docker daemon down, etc.),
stop and report. Do not proceed.

---

## Invariants — Do Not Violate

These apply to every phase:

1. **Branch**: stay on `proto`. Never switch to `main`. Never rebase or
   force-push. Never use `git commit --amend` unless explicitly authorised
   by the user mid-session.
2. **Commit often; close every phase with a phase-boundary commit**.
   Intermediate WIP commits within a phase are encouraged — commit per
   logical chunk (per deliverable, after tests go green, after a clean
   refactor, after a successful manual smoke). Every phase ends with a
   single phase-closing commit whose subject line is
   `proto: phase <N> — <title>`; that commit is only taken once the
   phase's full acceptance check passes. WIP commits only need to be
   internally consistent (no broken imports, no failing tests they
   touch, no secrets). See `## Commit Cadence` below.
3. **Active TODO discipline**. Update the TODO list on every meaningful
   transition, not at phase boundaries:
   - Mark a phase `in_progress` the moment you begin reading its
     `roadmap.md` section.
   - Create sub-todos as you identify deliverables for the phase
     (e.g., under Phase D: `phase_d.1 scaffold`,
     `phase_d.2 allowlist + spawn`, `phase_d.3 broker publish`,
     `phase_d.4 systemd unit + install.sh`, `phase_d.5 tests + AC`).
   - Mark each sub-todo `completed` as its WIP commit lands.
   - Mark the phase itself `completed` only after the phase-closing
     commit lands cleanly.
   - Exactly one todo is `in_progress` at a time.
   - Batch todo updates into the same tool-call turn as the code/commit
     action they describe; do not leave status mutations as trailing
     housekeeping.
4. **Python**: `uv add` / `uv sync` / `uv run`. Never `pip install`.
5. **No destructive ops without explicit acceptance criteria**. No
   `docker system prune`, no `rm -rf` outside the repo, no `git clean -fdx`,
   no dropping of volumes.
6. **Secrets**: never commit `.env`. `.env.example` only. If a secret
   slips into a diff, abort the commit, scrub, and retry.
7. **Exposure**: never bind a new service to `0.0.0.0`. Always
   `127.0.0.1:<port>`. The exposure smoke test enforces this.
8. **Scope**: do not pull work forward from later phases to "get it done
   faster". Each phase exists so that a failure is isolated to one commit.

If any invariant would be violated by a required deliverable, stop and
report rather than proceed.

---

## Commit Cadence

Two commit shapes; use both.

### WIP commits (during a phase)

Commit per logical chunk. Ship them as you go. Examples:

- `proto: phase D wip — scaffold hermes-gateway package (uv init + deps)`
- `proto: phase D wip — profile allowlist + spawn arg builder + unit tests`
- `proto: phase D wip — broker publish (run.created/started/completed/failed)`
- `proto: phase D wip — systemd --user unit + install.sh`

Each WIP commit must:

- Stage only the files that belong to that chunk
  (`git add <paths>`, not `git add -A`, unless the chunk truly touches
  everything that is currently dirty).
- Leave the tree in a state where any tests it touches pass
  (`uv run pytest` in the relevant subtree returns 0).
- Contain no secrets (`.env`, API keys, tokens). If a `.env` is dirty,
  `git diff --cached` before committing.
- Have a clear single-purpose message; the subject pattern is
  `proto: phase <N> wip — <micro-title>` (max 72 chars).

### Phase-closing commit (end of a phase)

After the full phase acceptance check passes:

```bash
git add -A                              # pick up any remaining stragglers
git status                              # review staged changes — no surprises
git diff --cached --stat                # sanity check file count and scope
git commit -m "$(cat <<'EOF'
proto: phase <N> — <short title>

<2–4 bullet points summarising the deliverables actually landed,
 including a one-line reference to the WIP chain if it existed>

Acceptance: <one-line description of the gate that passed>
EOF
)"
```

Rules for the phase-closing commit:

- Subject line: `proto: phase <N> — <short title>` (no `wip`), max 72 chars.
- Body: 2–4 bullets. Each bullet states a deliverable in past tense.
- Final line: `Acceptance: <gate>`. Makes the log grep-able.
- No `Co-authored-by` or similar trailers unless the user requests them.
- **Push after every phase-closing commit**: `git push origin proto`.
  WIP commits may be pushed as you go (encouraged) or batched to the
  phase close — either is fine. Never force-push.

---

## If a Phase Fails Acceptance

1. Do not commit.
2. Diagnose: read the failing command's output, the relevant service logs
   (`docker compose logs <svc>`, `journalctl --user -u <unit>`).
3. Fix the root cause. Do not relax the acceptance criterion to pass.
4. Re-run the full acceptance check from a clean state.
5. If stuck after two focused attempts, stop and report. Preserve any work
   in progress (don't `git checkout` away from it).

---

## Phases

Each phase below gives: the TODO id for status tracking, a pointer to
`roadmap.md` for the detailed deliverables, concrete commands to run, the
acceptance check (runnable), and the commit template.

### Phase A — Tidy Foundations

- **TODO id**: `phase_a`
- **Roadmap section**: `roadmap.md` `## Phase A`
- **Goal**: pin the five unpinned images, tidy the builder role overlay,
  and add a `nodes/linux-prototype/` manifest for this machine.

Concrete steps:

```bash
# Resolve current digests for the five unpinned images, then edit
# stack/prototype-local/docker-compose.substrate.yml to pin each one as
# `image@sha256:<digest>` following the Open WebUI / ComfyUI pattern
# already in the file.

docker pull minio/minio:latest
docker pull minio/mc:latest
docker pull qdrant/qdrant:latest
docker pull neo4j:latest
docker pull clickhouse/clickhouse-server:latest

docker inspect --format='{{index .RepoDigests 0}}' minio/minio:latest
docker inspect --format='{{index .RepoDigests 0}}' minio/mc:latest
docker inspect --format='{{index .RepoDigests 0}}' qdrant/qdrant:latest
docker inspect --format='{{index .RepoDigests 0}}' neo4j:latest
docker inspect --format='{{index .RepoDigests 0}}' clickhouse/clickhouse-server:latest
```

Edit `stack/prototype-local/docker-compose.substrate.yml` to use those
digests. Decide per `roadmap.md` Phase A what to do with
`stack/roles/builder/docker-compose.role.yml` (delete the empty
`services: {}` overlay or populate it with a real builder service).

Create `nodes/linux-prototype/`:

- `nodes/linux-prototype/README.md` — single paragraph describing this
  machine's role in the topology.
- `nodes/linux-prototype/roles.env.example` — `ROLES=core,media-cpu,tools`.

**Acceptance**:

```bash
# Every image in the compose file is pinned by digest:
docker compose -f stack/prototype-local/docker-compose.substrate.yml config \
  | rg '^\s+image:' | rg -v '@sha256:' | rg -v '^\s*#'
# ^ must return NO results.

test -f nodes/linux-prototype/README.md                              # exists
test -f nodes/linux-prototype/roles.env.example                      # exists
```

**Commit**: `proto: phase A — tidy foundations`.

---

### Phase B — Host-Native Honcho

- **TODO id**: `phase_b`
- **Roadmap section**: `roadmap.md` `## Phase B`
- **Goal**: Honcho under `systemd --user`, sharing the substrate
  Postgres; retire the separate `1215-honcho-pg` container.

Concrete steps (see `roadmap.md` for full deliverable list):

```bash
mkdir -p stack/services/honcho
# Create honcho.service, honcho-deriver.service, install.sh under this dir
# (see roadmap.md Phase B for exact contract).
```

Extend `postgres-bootstrap` in
`stack/prototype-local/docker-compose.substrate.yml` to also create a
`honcho` database and enable `pgvector` on it.

Add Honcho env vars to `stack/prototype-local/.env.example`:

```bash
HONCHO_DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5433/honcho
HONCHO_LLM_PROVIDER=...        # per modules/honcho/.env.template
HONCHO_LLM_MODEL=...
```

Update `stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`
to stop launching `1215-honcho-pg` and point at the shared Postgres.

Install and start the user units:

```bash
bash stack/services/honcho/install.sh
systemctl --user daemon-reload
systemctl --user enable --now honcho honcho-deriver
```

**Acceptance**:

```bash
systemctl --user is-active honcho                                    # active
systemctl --user is-active honcho-deriver                            # active
curl -sS http://127.0.0.1:18000/health                               # 200
docker ps --format '{{.Names}}' | rg -v '1215-honcho-pg'             # no 1215-honcho-pg
# Run the Hermes memory write/read smoke extracted from
# setup_hermes_honcho_paperclip.py and confirm success against shared pg.
```

**Commit**: `proto: phase B — host-native Honcho`.

---

### Phase C — Hermes `orchestrator-ceo` Profile

- **TODO id**: `phase_c`
- **Roadmap section**: `roadmap.md` `## Phase C`
- **Goal**: Hermes profile directory populated, fake-secret canary in
  place, profile `--dry-run` resolves cleanly.

Concrete steps:

```bash
sudo mkdir -p /var/lib/hermes/orchestrator-ceo/.hermes/{skills,workspaces}
sudo mkdir -p /var/lib/paperclip/workspaces/orchestrator-ceo
sudo chown -R $USER:$USER /var/lib/hermes/orchestrator-ceo /var/lib/paperclip/workspaces/orchestrator-ceo
```

Populate `config.toml`, `skills/` (empty — populated in Phase F), and
a host-only `.env` with the **fake-secret canary** (per
`roadmap.md` Phase C).

Create `stack/services/hermes-gateway/scripts/setup_ceo_profile.sh` as
the reproducible installer (doesn't run the gateway yet; just sets up
the profile directory idempotently).

**Acceptance**:

```bash
hermes chat --profile orchestrator-ceo --dry-run                     # resolves and exits 0
# Fake-secret canary string must not appear in any hermes-produced file:
rg "$CANARY_STRING" /var/lib/hermes/orchestrator-ceo /var/lib/paperclip/workspaces/orchestrator-ceo
# (expected: no matches)
```

**Commit**: `proto: phase C — orchestrator-ceo Hermes profile`.

---

### Phase D — `hermes-gateway` Daemon

- **TODO id**: `phase_d`
- **Roadmap section**: `roadmap.md` `## Phase D`
- **Goal**: FastAPI daemon on UDS, profile allowlist enforced, broker
  lifecycle events publishing correctly.

This is the single biggest phase. It touches new code, new systemd
units, and the container-to-host boundary. Follow `roadmap.md` Phase D
deliverables exactly.

Concrete initial scaffold:

```bash
mkdir -p stack/services/hermes-gateway/hermes_gateway stack/services/hermes-gateway/tests
cd stack/services/hermes-gateway
uv init --app --python ">=3.11"
uv add fastapi 'uvicorn[standard]' httpx pydantic
uv add --dev pytest pytest-asyncio
```

Implement per `roadmap.md` Phase D:

- `hermes_gateway/app.py` — FastAPI on UDS at
  `/run/hermes-gateway/gateway.sock`, mode `0660`, group `hermes-gateway`.
- `hermes_gateway/spawn.py` — profile allowlist (`["orchestrator-ceo"]`),
  fixed PATH, no shell expansion, workspace allowlist, env resolved from
  host secret files only.
- `hermes_gateway/broker.py` — publishes `run.created/started/completed/failed`
  to `http://127.0.0.1:8090`, `run_id` as idempotency key.
- `hermes-gateway.service` — systemd `--user` unit.
- `install.sh` — idempotent installer.
- `tests/` — allowlist unit tests, spawn-argument construction tests.

**Acceptance** (per `roadmap.md` Phase D):

```bash
# 1. StartRun via socket returns run_id and lands run.created in broker
curl --unix-socket /run/hermes-gateway/gateway.sock \
     -X POST http://localhost/runs/start \
     -H 'Content-Type: application/json' \
     -d '{"profile":"orchestrator-ceo","session_id":"t1","prompt":"echo hi"}'
# response contains run_id
curl -s http://127.0.0.1:8090/events | jq '.[] | select(.event_type=="run.created")' | head

# 2. Non-allowlisted profile returns 403 without spawning
curl --unix-socket /run/hermes-gateway/gateway.sock \
     -X POST http://localhost/runs/start \
     -d '{"profile":"other","session_id":"t2","prompt":"x"}' \
     -w '\n%{http_code}\n'
# must end with: 403

# 3. Completion publishes run.completed with matching run_id

uv run --project stack/services/hermes-gateway pytest
# all unit tests pass
```

**Commit**: `proto: phase D — hermes-gateway daemon`.

---

### Phase E — Paperclip Container

- **TODO id**: `phase_e`
- **Roadmap section**: `roadmap.md` `## Phase E`
- **Goal**: Paperclip in compose, reaches Hermes only through the gateway
  UDS, `orchestrator-ceo` company bootstrapped.

Concrete steps:

- Add `paperclip` service to
  `stack/prototype-local/docker-compose.substrate.yml` per `roadmap.md`
  Phase E (image built from `modules/paperclip`, port
  `127.0.0.1:3100:3100`, bind-mount `/run/hermes-gateway` read-write,
  env `PAPERCLIP_HERMES_GATEWAY_SOCKET` and `PAPERCLIP_BROKER_URL`).
- Add `paperclip` to `stack/topology/targets.json` `prototype-local.services`.
- Remove the host-side Paperclip launch from
  `stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`.
- Create
  `stack/prototype-local/scripts/bootstrap_paperclip_ceo.py` that
  bootstraps the `orchestrator-ceo` company via the Paperclip API.

**Acceptance**:

```bash
docker compose -f stack/prototype-local/docker-compose.substrate.yml up -d paperclip
curl -sS http://127.0.0.1:3100/api/health                            # 200
# Start a run from the Paperclip UI (or via API), then:
curl -s http://127.0.0.1:8090/events | jq '.[] | select(.event_type=="run.created")' | tail -1
# ^ should show the run created via the gateway
```

**Commit**: `proto: phase E — Paperclip container`.

---

### Phase F — `broadcast_*` and `artifact_*` Hermes Skills

- **TODO id**: `phase_f`
- **Roadmap section**: `roadmap.md` `## Phase F`
- **Goal**: Hermes talks to the continuity plane via first-party skills;
  broker grows `/checkpoints` endpoints.

Concrete steps:

- Add `POST /checkpoints` and `GET /checkpoints` to
  `stack/broker/broker_service/app.py` (with tests in
  `stack/broker/tests/test_app.py`). Backed by
  `broker.provider_checkpoints` per `stack/sql/broker/001_core.sql`.
- Populate `/var/lib/hermes/orchestrator-ceo/.hermes/skills/` with
  `broadcast_publish.py`, `broadcast_read_feed.py`, `broadcast_ack.py`,
  `artifact_publish.py`, `artifact_read.py`. Skill signatures follow the
  broadcast/artifact API contract implied by the broker schema
  (`events`, `artifacts`, `provider_checkpoints` tables).

**Acceptance** (per `roadmap.md` Phase F):

```bash
uv run --project stack/broker pytest -k checkpoints                  # pass
# Hermes (as orchestrator-ceo) can:
#  1. broadcast_publish → event appears in GET /events
#  2. artifact_publish → MinIO write + /artifacts upsert; artifact_read
#     round-trips via signed URL
#  3. broadcast_ack advances a checkpoint; GET /checkpoints reflects it
```

**Commit**: `proto: phase F — broadcast and artifact Hermes skills`.

---

### Phase G — Langfuse Instrumentation

- **TODO id**: `phase_g`
- **Roadmap section**: `roadmap.md` `## Phase G`
- **Goal**: `run_id ↔ trace_id` correlation across gateway, broker, and
  Hermes; Langfuse shows nested spans for multi-step runs.

Concrete steps:

- In the gateway (Phase D), generate `run_id` and use it as the Langfuse
  `trace_id`. Inject `LANGFUSE_TRACE_ID` and `LANGFUSE_SESSION_ID` into
  the Hermes subprocess env.
- Configure Hermes to emit Langfuse spans using that trace ID (via
  profile config or a lightweight wrapper).
- In the broker's event write path, when `run_id` is present on the
  incoming event, attach it as `metadata_json.langfuse_trace_id`.
- Add a Langfuse saved view / dashboard filtering by
  `trace_id == run_id`.

**Acceptance**:

```bash
# Start a CEO run via Paperclip; capture the run_id.
# Confirm:
#   - POST /events payloads for that run carry metadata.langfuse_trace_id == run_id
#   - Langfuse UI shows a trace with that exact ID and multi-step spans nested under it
```

**Commit**: `proto: phase G — Langfuse run_id/trace_id correlation`.

---

### Phase H — Unified Launch Script

- **TODO id**: `phase_h`
- **Roadmap section**: `roadmap.md` `## Phase H`
- **Goal**: `./bin/1215 {up,down,status,logs,smoke}` replaces the
  existing patchwork; `setup_hermes_honcho_paperclip.py` is retired.

Concrete steps:

- Add `up`, `down`, `status`, `logs`, `smoke` subcommands to
  `stack/control/control1215/cli.py`. Implement the
  service-to-source routing map in a new
  `stack/control/control1215/lifecycle.py`.
- Every subcommand supports `--json` for CI.
- Every subcommand is idempotent.
- Create `bin/1215` (executable shim that execs into
  `uv run --project stack/control start-1215`). Note: `bin/start-1215.py`
  was removed in Phase 0 — there is no tombstone to maintain; `bin/1215`
  is the only repo-root entrypoint going forward.
- Delete `stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py`
  only after `./bin/1215 up` has been shown to replace it end-to-end
  (i.e. the acceptance check below has passed).

**Acceptance** (per `roadmap.md` Phase H):

```bash
# 1. Cold bringup
./bin/1215 down || true
./bin/1215 up --target prototype-local                               # exits 0 in <3 min
./bin/1215 status                                                    # all services green

# 2. Smoke
./bin/1215 smoke                                                     # exits 0

# 3. Idempotency
./bin/1215 down
STATUS_A=$(./bin/1215 status --json)
./bin/1215 up
STATUS_B=$(./bin/1215 status --json)
# STATUS_A and STATUS_B must agree modulo timestamps/uptime counters

# 4. Half-up sanity
docker compose -f stack/prototype-local/docker-compose.substrate.yml up -d
systemctl --user stop hermes-gateway honcho
./bin/1215 status                                                    # non-zero exit, names missing units

# 5. No drift
docker compose -f stack/prototype-local/docker-compose.substrate.yml ps --format json > /tmp/a.json
systemctl --user list-units --state=active --output json > /tmp/b.json
./bin/1215 status --json > /tmp/c.json
# /tmp/c.json must be consistent with /tmp/a.json + /tmp/b.json (no phantom services, no missed ones)
```

**Commit**: `proto: phase H — unified launch script`.

---

## Final Steps After Phase H

1. Run the full cross-phase gate suite (`roadmap.md` `## Cross-Phase Gates`):
   exposure smoke test + fake-secret canary across every active subsystem.
   All green.
2. Verify the commit log shape on `proto`:
   ```bash
   git log --oneline proto ^$(git merge-base proto main)
   ```
   should include **eight** `proto: phase <N> — <title>` commits for
   Phases A–H, in addition to the Phase 0 trim and stabilize commits that
   are already present.
3. Do not `git push` automatically. Report completion to the user with:
   - Final `git log --oneline` (last 10 commits).
   - `./bin/1215 status` output.
   - Summary of any deviations from this plan and why.
4. Stop. Do not start on deferred items (edge layer, learning plane,
   multi-node, additional specialist workers, backup/restore drills).

---

## Cross-Reference Map

| Subject | Canonical location |
|---|---|
| What the system becomes | `docs/architecture/north-star.md` |
| What is in the repo today | `docs/architecture/current-state.md` |
| Per-phase deliverables and acceptance criteria | `docs/architecture/roadmap.md` |
| Execution discipline (this file) | `docs/architecture/execution-plan.md` |
| Node responsibilities and promotion policy | `docs/architecture/node-roles.md` |
| Legacy high-level overview (superseded) | `docs/architecture/overview.md` |
| Broker schema source of truth | `stack/sql/broker/001_core.sql` |
| Broker API source of truth | `stack/broker/broker_service/app.py` |
| Compose topology source of truth | `stack/prototype-local/docker-compose.substrate.yml` |

---

## Glossary (quick reference for the fresh agent)

- **Gateway UDS**: `/run/hermes-gateway/gateway.sock`, mode `0660`, group
  `hermes-gateway`. The only container-to-host execution boundary.
- **CEO profile**: `/var/lib/hermes/orchestrator-ceo/.hermes/`. Host-only
  Hermes profile for the flagship Paperclip company.
- **CEO workspace**: `/var/lib/paperclip/workspaces/orchestrator-ceo/`.
  `cwd` for CEO runs.
- **Substrate Postgres**: `postgres:17` container, listening
  `127.0.0.1:5433`, hosts databases `postgres`, `langfuse`, and (after
  Phase B) `honcho`.
- **Broker API**: `http://127.0.0.1:8090`, internal DNS `broker:8090`.
- **Broadcast** / **artifact skills**: Hermes skills wrapping the Broker
  API as first-party agent tools.
- **Fake-secret canary**: a known-invalid API key placed in the CEO
  `.env` at Phase C. Its appearance anywhere (logs, traces, event
  payloads) is a secret-handling regression.

---

## Done Bar

Prototype is complete when:

- All eight phase commits (A–H) land cleanly on `proto`.
- `./bin/1215 up` brings the stack to fully green in one shot.
- `./bin/1215 smoke` passes.
- Cross-phase gates pass.
- A CEO run end-to-end: Paperclip UI → gateway UDS → Hermes on host →
  Honcho memory → broker events → Langfuse trace, all correlated by
  `run_id == trace_id`, artifacts in MinIO registered in
  `broker.artifacts`.

Stop here. Further work (edge, learning plane, VPS hub, multi-node) is
deferred and belongs in a follow-up plan.
