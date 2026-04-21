# Architecture Docs Comparative Audit

Audit date: 2026-04-21
Scope: 14 repo-owned documents under [docs/architecture/](../) (the 75KB external research doc `Self-Hosted Long-Horizon Memory Architecture...md` was out of scope).
Deliverables: this README + [drift-matrix.md](drift-matrix.md) + [claims-index.json](claims-index.json).

## How to read this

- **Drift** means a doc makes a *current-state* claim the repo contradicts — fix either the doc or the repo.
- **Gap** means the doc describes a *required-end-state* the repo hasn't reached yet — expected per phase; track, don't panic.
- **Policy-violation** means code/config breaks a declared rule — fix the repo.
- **Unverifiable** means the claim cannot be checked from static files alone — needs runtime or deeper code-level review.

Full per-claim evidence lives in [drift-matrix.md](drift-matrix.md). Machine-readable claim list is in [claims-index.json](claims-index.json).

## Top findings

### 1. The shared-core plan is partially stale

[prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) is the most recent and concrete doc, but three of its five "Critical Gaps" have already moved since it was written:

- **Gap 1 partially resolved**: `prototype-local` in [targets.json](../../../stack/topology/targets.json) no longer claims paperclip/honcho/hermes/hermes-gateway; those services now appear in the `vps-hub` target instead — *but `vps-hub` has `compose_files: []`*. The same "topology ahead of runtime" pattern reappeared at the hub level.
- **Gap 4 resolved**: `n8n-mcp` is in [gate_shared_core.py](../../../stack/prototype-local/scripts/gate_shared_core.py) (line 45). It is no longer "optional."
- **Gap 5 resolved**: `.env` is in [.gitignore](../../../.gitignore) (line 15) and `git ls-files stack/prototype-local/.env` returns empty — it is not tracked. The working-tree file exists but was never committed.

Gaps 2 and 3 still stand.

### 2. The network port map is the single most drifted current-state doc

[network-port-map.md](../network-port-map.md) documents internal ports but has three concrete mismatches with [docker-compose.substrate.yml](../../../stack/prototype-local/docker-compose.substrate.yml):

| Service | Port map says | Compose binds |
|---|---|---|
| `n8n-mcp` | `:3000` internal-only | `127.0.0.1:13000:3000` (host port remapped because `:3000` is taken by `langfuse-web`) |
| `broker` | not listed at all | `127.0.0.1:8090:8090` |
| `comfyui` | not listed at all | `127.0.0.1:8188:8188` |

There's also a soft disagreement inside the repo itself: the port map says Paperclip will bind `:3100`; [.env.example](../../../stack/prototype-local/.env.example) (lines 100-104) says `:8484`. Needs a single source of truth before Phase 4/7 is implemented.

### 3. Node-type naming diverges between docs and repo

- [node-roles.md](../node-roles.md) and [inter-node-data-flow.md](../inter-node-data-flow.md) enumerate **VPS / Linux prototype / Engineering / Research** as the canonical four node types.
- [nodes/](../../../nodes/) contains **vps, engineering-pc, local-builder** — no research, no linux-prototype. `local-builder` is not mentioned in node-roles.md at all.
- [deployment-model.md](../deployment-model.md) line 224-230 acknowledges that the current prototype *is* the VPS node, which partially papers over the gap — but the terminology needs a single story.

### 4. "Required but not implemented" items are concentrated in four places

These cluster items are referenced by 2+ docs, form a bounded checklist, and are the most valuable policy-to-code bridge work:

| Missing item | Referenced by |
|---|---|
| Exposure smoke test (crawl port map, fail CI on unexpected external reachability) | [network-port-map.md#L161](../network-port-map.md), [implementation-roadmap.md#L28](../implementation-roadmap.md), [review-01.md#L28](../review-01.md) |
| Fake-secret canary test | [security-observability.md#L74-L91](../security-observability.md), [node-rollout-plan.md#L78-L94](../node-rollout-plan.md), [implementation-roadmap.md#L157](../implementation-roadmap.md), [prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) |
| Restart-resilience test | [node-rollout-plan.md#L108-L119](../node-rollout-plan.md), [prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) |
| Backup/restore drill | [security-observability.md#L166-L172](../security-observability.md), [review-01.md#L42-L67](../review-01.md) |

### 5. Image pinning is partially done

[prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) Phase 1 and [review-01.md#L91](../review-01.md) both call for pinned image tags. The four "explicit" targets (Open WebUI, n8n, n8n-mcp, ComfyUI) **are pinned** — two by SHA digest, two by version tag. Still unpinned in [docker-compose.substrate.yml](../../../stack/prototype-local/docker-compose.substrate.yml):

- `neo4j:latest` (line 133) — the only explicit `:latest`
- `minio/minio` (line 72)
- `qdrant/qdrant` (line 124)
- `clickhouse/clickhouse-server` (line 148)
- `minio/mc` (line 91)

### 6. Role overlay scaffolding is inconsistent

[deployment-model.md](../deployment-model.md) says role overlays live as compose fragments under `stack/roles/<role>/`. Reality:

- `stack/roles/core/` — empty folder (matches `"compose_files": []` in [roles.json](../../../stack/topology/roles.json))
- `stack/roles/vps/` — empty folder (matches)
- `stack/roles/builder/docker-compose.role.yml` — file exists but contains `services: {}` (does nothing)
- `stack/roles/media-cpu`, `stack/roles/media-gpu`, `stack/roles/tools` — each has a 3-7 line fragment that overrides one service

The `builder` fragment should either gain content or be removed; empty folders for `core`/`vps` could be replaced with `.gitkeep`-only directories or documented as intentional placeholders.

### 7. Module env compilation is mostly accurate but incomplete

[module-env-compilation.md](../module-env-compilation.md) per-module key lists are broadly correct but have three concrete omissions worth fixing:

- `honcho/.env.template` has 10 active `DIALECTIC_LEVELS__{minimal,low,medium,high,max}__{PROVIDER,MODEL}` keys not listed in the compilation.
- `n8n-mcp/.env.example` claims a `LOG_LEVEL` key (only `MCP_LOG_LEVEL` exists) and omits `MCP_SERVER_PORT`, `MCP_SERVER_HOST`, `ENABLE_MULTI_TENANT`.
- `n8n-mcp/.env.docker` omits `HTTP_PORT`, `HTTPS_PORT`, `USE_NGINX`.

## What should change in docs vs what should change in the repo

### Docs should change

| Doc | Change |
|---|---|
| [prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) | Update Gaps 1, 4, 5 to reflect resolution. Note that the "topology ahead of runtime" pattern has moved to the `vps-hub` target. |
| [network-port-map.md](../network-port-map.md) | Add `Broker API :8090` and `ComfyUI :8188` rows. Update `n8n-mcp` host-bind note to `127.0.0.1:13000:3000`. Reconcile Paperclip port with [.env.example](../../../stack/prototype-local/.env.example). |
| [node-roles.md](../node-roles.md) / [inter-node-data-flow.md](../inter-node-data-flow.md) | Reconcile node-type names (research? linux prototype? local-builder?) with [nodes/](../../../nodes/) folder reality. |
| [module-env-compilation.md](../module-env-compilation.md) | Add dialectic keys to honcho section; fix n8n-mcp `.env.example` / `.env.docker` lists. |
| [deployment-model.md](../deployment-model.md) | Note that `core/vps` role overlays are intentionally empty and `builder` currently has an empty compose fragment. |

### Repo should change

| Item | Where | Priority |
|---|---|---|
| Populate `vps-hub` target in [targets.json](../../../stack/topology/targets.json) with real `compose_files` or mark it `status: placeholder` | `stack/topology/` | high (doc says hub is canonical) |
| Pin `neo4j:latest`, `minio/minio`, `qdrant/qdrant`, `clickhouse/clickhouse-server`, `minio/mc` | [docker-compose.substrate.yml](../../../stack/prototype-local/docker-compose.substrate.yml) | high (supply-chain) |
| Add an exposure smoke test script and wire into `gate_shared_core.py` | `stack/prototype-local/scripts/` | medium |
| Add fake-secret canary test and wire into the gate | `stack/prototype-local/scripts/` | medium |
| Add restart-resilience test to the gate | `stack/prototype-local/scripts/` | medium |
| Decide Paperclip host port once (`:3100` or `:8484`) and align doc + env | port map + env | medium |
| Remove empty `stack/roles/builder/docker-compose.role.yml` OR add real content | `stack/roles/builder/` | low |
| Rotate the secrets that ever lived in `stack/prototype-local/.env` (even though it was never committed) | out-of-repo | medium |
| Create a real `nodes/<hostname>/roles.env` for this Linux box (Phase 10) | `nodes/` | low (after shared-core gate) |

### Items that are correctly "gap-by-design"

These are pure phase gaps — no action needed now, only tracking:

- Caddy / cloudflared / Tailscale (edge layer) — Phase 1 for VPS, not prototype
- Paperclip / Hermes gateway / Hermes container / Honcho service — Phase 4-5
- Approval workflows in n8n — Phase 3 extension
- Brokered enrichment workers into Qdrant/Neo4j — Phase 5
- Learning plane runtime — Phase 7
- Research node — out of v1 scope

## Suggested next audit

After the shared-core gate (Phase 4-6) is implemented, re-run this audit by diffing against [claims-index.json](claims-index.json). Claim IDs are stable and statuses should predominantly shift from `gap` to `match`. If any `drift` row reappears, it's a regression.
