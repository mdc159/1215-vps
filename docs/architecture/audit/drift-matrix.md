# Architecture Docs Drift Matrix

Audit date: 2026-04-21

Each section lists claims extracted from a document in [docs/architecture/](../) and compares them to repository evidence. Status codes:

- `match` — doc and repo agree
- `drift` — doc makes a current-state claim that the repo contradicts
- `gap` — required end-state not yet implemented (expected per phase)
- `policy-violation` — repo contradicts a policy rule
- `unverifiable` — claim cannot be checked from static artifacts

Claim classes: `current-state`, `required-end-state`, `policy`, `intent`.

---

## 1. overview.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Three architectural centers: continuity plane, nervous system (n8n), human/agent surfaces | [overview.md#L6-L10](../overview.md) | intent | [stack/broker/](../../../stack/broker/), [stack/prototype-local/n8n/](../../../stack/prototype-local/n8n/), compose includes `open-webui` and `n8n` | match | Conceptual intent matches repo shape. |
| Learning plane is a deliberate adjacent layer (autoreason, hermes-agent-self-evolution) | [overview.md#L12-L15](../overview.md) | intent | [.gitmodules](../../../.gitmodules) declares `autoreason`, `hermes-agent-self-evolution` submodules | match (code in modules) / gap (runtime) | Reference modules exist; no `stack/learning/` runtime yet. |
| v1 includes Paperclip, Hermes gateway, Honcho adapter, Qdrant, Neo4j, MinIO, Langfuse | [overview.md#L213-L224](../overview.md) | required-end-state | Compose has qdrant, neo4j, minio, langfuse; no paperclip, hermes, hermes-gateway, honcho services | gap | Known per [prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) phases 5-8. |
| Mermaid diagram shows `Caddy`, `Cloudflare tunnel`, `Tailscale` routing in front of surfaces | [overview.md#L29-L125](../overview.md) | intent / required-end-state | No caddy, cloudflared, or tailscale service in [docker-compose.substrate.yml](../../../stack/prototype-local/docker-compose.substrate.yml) | gap | Consistent with `vps-complete` scope; prototype-local is explicitly `local-only-or-tailnet`. |
| Hermes is host-native, exposed via repo-owned gateway shim | [overview.md#L159](../overview.md) | required-end-state | [stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py](../../../stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py) does host-side setup; no containerized gateway service | gap | Gateway is on roadmap (implementation-roadmap Phase 4). |

---

## 2. service-catalog.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Required-in-v1 services include `Paperclip`, `Honcho`, `Hermes gateway`, `Hermes`, `Langfuse worker/web` | [service-catalog.md#L14-L33](../service-catalog.md) | required-end-state | Compose has `langfuse-worker`, `langfuse-web`; lacks paperclip, honcho, hermes, hermes-gateway | gap | Expected gap in prototype-local; VPS-hub target also lacks a runnable compose. |
| `n8n-mcp` is required in v1 and Internal-only | [service-catalog.md#L22](../service-catalog.md) | required-end-state / policy | Compose has `n8n-mcp` bound to `127.0.0.1:13000:3000` | match | Localhost-only bind satisfies Internal-only policy; port differs from docs (see §3). |
| `Honcho` v1 requires Postgres+Redis, DB-backed, Internal-only | [service-catalog.md#L29](../service-catalog.md) | required-end-state | No `honcho` service in compose | gap | Env placeholders exist in [.env.example](../../../stack/prototype-local/.env.example#L73-L88). |
| Optional-but-retained set includes `SearXNG`, `Flowise`, `Ollama`, `Supabase Studio`, and learning-plane components | [service-catalog.md#L40-L47](../service-catalog.md) | intent | None present in compose | match (as optional) | Correctly not in v1 baseline. |
| Qdrant and Neo4j each hold different data classes (semantic vs relationships) | [service-catalog.md#L76-L80](../service-catalog.md) | intent | Compose has both running but no enrichment workers yet | gap (enrichment) | Phase 5 of roadmap. |

---

## 3. network-port-map.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| `Open WebUI :8080` (public via Caddy) | [network-port-map.md#L27, L121](../network-port-map.md) | current-state (localhost), required-end-state (public) | Compose `open-webui` -> `127.0.0.1:8080:8080` | match (localhost bind); gap (public via Caddy) | Caddy not deployed yet. |
| `n8n :5678` (public or tailnet via Caddy) | [network-port-map.md#L28, L122](../network-port-map.md) | current-state / required-end-state | Compose `n8n` -> `127.0.0.1:5678:5678` | match (localhost); gap (public/tailnet) | — |
| `Paperclip :3100` (tailnet-only via Caddy) | [network-port-map.md#L28, L123](../network-port-map.md) | required-end-state | No paperclip in compose | gap | Env assumes `:8484` in [.env.example#L100-L104](../../../stack/prototype-local/.env.example) — **doc/env disagree on port**. |
| `n8n-mcp :3000` (Internal-only) | [network-port-map.md#L29, L124](../network-port-map.md) | current-state | Compose binds `127.0.0.1:13000:3000` (container port 3000) | drift | Doc omits the host-port remap; `:3000` is occupied by `langfuse-web`. Either document `:13000` as the authoritative localhost bind or mark n8n-mcp Docker-internal-only. |
| `Honcho :8000` (Internal-only) | [network-port-map.md#L29, L125](../network-port-map.md) | required-end-state | No honcho service; env has `HONCHO_BASE_URL=http://127.0.0.1:8000` | gap | Target port matches env expectation. |
| `Langfuse web :3000` (Tailnet-only) | [network-port-map.md#L30, L126](../network-port-map.md) | current-state (localhost) | Compose `langfuse-web` -> `127.0.0.1:3000:3000` | match | — |
| `Langfuse worker :3030` Internal-only | [network-port-map.md#L105, L127](../network-port-map.md) | current-state | `127.0.0.1:3030:3030` | match | Localhost bind = not publicly reachable. |
| `Langfuse Postgres :5433` localhost | [network-port-map.md#L106](../network-port-map.md) | current-state | Compose `postgres` (shared) -> `127.0.0.1:5433:5432` | match | Note: this is the single shared postgres, not a dedicated Langfuse postgres. Port number matches; the Langfuse DB is a schema/db inside shared postgres. |
| `MinIO S3 :9010`, console `:9011` localhost | [network-port-map.md#L108-L109](../network-port-map.md) | current-state | `127.0.0.1:9010:9000`, `127.0.0.1:9011:9001` | match | — |
| `Qdrant 6333/6334` localhost | [network-port-map.md#L110](../network-port-map.md) | current-state | Compose binds both on `127.0.0.1` | match | — |
| `Neo4j 7474/7473/7687` localhost | [network-port-map.md#L111](../network-port-map.md) | current-state | Matches compose | match | — |
| Broker internal port not documented in port map | [network-port-map.md port table](../network-port-map.md) | drift / missing | Compose binds `broker` `127.0.0.1:8090:8090` | drift | Broker is listed as Internal-only in §Exposure Policy but never given a port number. Add `Broker API :8090` to the Internal Listener Ports table. |
| ComfyUI not in port map | none | drift / missing | Compose binds `comfyui` `127.0.0.1:8188:8188` | drift | ComfyUI is a de-facto prototype surface; add `ComfyUI :8188` to the port map (local-only). |
| `SearXNG :8080`, `Flowise :3001`, `Ollama :11434` (optional) | [network-port-map.md#L112-L113, L135-L137](../network-port-map.md) | intent | None in compose | match (correctly absent) | Not yet enabled. |
| "Exposure smoke test fails CI if anything Internal becomes Public" | [network-port-map.md#L161](../network-port-map.md) | required-end-state | No script matching `smoke|exposure` in [stack/prototype-local/scripts/](../../../stack/prototype-local/scripts/) | gap | Carried over from [review-01.md](../review-01.md). |

---

## 4. runtime-flows.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Open WebUI -> n8n -> Broker flow with session/run/event writes | [runtime-flows.md#L7-L26](../runtime-flows.md) | current-state (partially) / required-end-state | [stack/prototype-local/scripts/test_openwebui_n8n_broker.py](../../../stack/prototype-local/scripts/test_openwebui_n8n_broker.py) exercises exactly this path; n8n workflows under [stack/prototype-local/n8n/](../../../stack/prototype-local/n8n/) include `Get_Prototype_Postgres_Tables_Webhook.json` that writes continuity rows | match | Prototype path exists; Langfuse trace-close step is not proven by static evidence — `unverifiable`. |
| Paperclip -> Hermes gateway -> Hermes -> Honcho flow | [runtime-flows.md#L49-L68](../runtime-flows.md) | required-end-state | No Paperclip, gateway, or honcho service in compose; [setup_hermes_honcho_paperclip.py](../../../stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py) implements host-side setup and smoke but not container gateway | gap | Phase 4 of roadmap. |
| Approval-gated workflow path records pending/outcome events in broker | [runtime-flows.md#L92-L113](../runtime-flows.md) | required-end-state | No n8n workflow JSON under [stack/prototype-local/n8n/](../../../stack/prototype-local/n8n/) shows approval semantics | gap | Approval workflows not yet authored. |
| Brokered enrichment into Qdrant/Neo4j | [runtime-flows.md#L132-L147](../runtime-flows.md) | required-end-state | No broker worker targeting qdrant/neo4j in [stack/broker/broker_service/](../../../stack/broker/broker_service/) | gap | Phase 5. |
| Hermes -> Honcho memory write/recall | [runtime-flows.md#L167-L183](../runtime-flows.md) | required-end-state | [setup_hermes_honcho_paperclip.py](../../../stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py) includes a `run_memory_smoke` write/read test via host Honcho | partial / match | Host-side works; in-repo container wiring absent. |
| Learning / self-improvement loop sequence | [runtime-flows.md#L201-L226](../runtime-flows.md) | intent | No learning orchestrator runtime in repo | gap | Phase 7. |

---

## 5. security-observability.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Public: Open WebUI; n8n conditionally | [security-observability.md#L7-L10](../security-observability.md) | policy | Prototype binds both to `127.0.0.1` only | match (stricter) | Prototype is `local-only-or-tailnet` per [targets.json](../../../stack/topology/targets.json). |
| Internal-only: Postgres, Valkey, MinIO S3, ClickHouse, Honcho, n8n-mcp, broker | [security-observability.md#L33-L40](../security-observability.md) | policy | All bound to `127.0.0.1` in compose (Honcho absent) | match | Localhost bind satisfies Internal-only in a single-host deployment. |
| Host-only: Hermes gateway socket, Hermes, Hermes profile/workspace dirs | [security-observability.md#L42-L45](../security-observability.md) | policy | Not containerized yet | gap | Policy ready; implementation pending. |
| No secrets committed in the repo | [security-observability.md#L49-L54](../security-observability.md) | policy | [.gitignore#L15](../../../.gitignore) contains `stack/prototype-local/.env`; `git ls-files stack/prototype-local/.env` returns empty | match | `.env` exists in working tree but is not tracked — matches policy. |
| Fake-secret canary must not persist in Hermes/Honcho/Langfuse/n8n state/Qdrant/Neo4j/MinIO/docs | [security-observability.md#L74-L91](../security-observability.md) | required-end-state | No canary test script; `gate_shared_core.py` does not include one | gap | Flagged by [review-01.md](../review-01.md) §4 and by [node-rollout-plan.md#L78-L94](../node-rollout-plan.md). |
| Workflow-to-trace mapping enforced by implementation, not convention | [security-observability.md#L112](../security-observability.md) | required-end-state | n8n workflow JSON files do not show structural `workflow_id`/`run_id` correlation nodes; broker app does not yet enforce trace linkage | gap | Phase 3 acceptance; partial evidence only. |
| Broker tables are immutable append-only with idempotent writes | [security-observability.md#L114-L124](../security-observability.md) | policy | [stack/sql/broker/001_core.sql](../../../stack/sql/broker/001_core.sql) defines core schema (not inspected line-by-line here — flagged for deeper audit) | unverifiable | Needs schema-level review to confirm uniqueness constraints and absence of UPDATE paths. |
| Nightly logical backup, off-box MinIO replication, restore drills | [security-observability.md#L166-L172](../security-observability.md) | required-end-state | No backup or restore scripts under `stack/` | gap | Carried over from [review-01.md](../review-01.md) §A. |

---

## 6. inter-node-data-flow.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Hub-and-spoke: VPS is hub; nodes publish/consume via broker | [inter-node-data-flow.md#L3-L9](../inter-node-data-flow.md) | intent | [stack/topology/targets.json](../../../stack/topology/targets.json) has a `vps-hub` target, but its `compose_files: []` is empty | gap | Hub target is declared but not yet runnable. |
| Node types: VPS hub, Linux prototype, Engineering node, Research node | [inter-node-data-flow.md#L13-L19](../inter-node-data-flow.md) | intent | [nodes/](../../../nodes/) contains `vps`, `engineering-pc`, `local-builder` — no `research` node | partial drift | Doc names differ (`Engineering node` vs `engineering-pc`, `Linux prototype` has no dedicated folder, Research node absent). |
| Default flows allowed: node→VPS, VPS→node; node→node forbidden | [inter-node-data-flow.md#L117-L123](../inter-node-data-flow.md) | policy | No inter-node transport implemented yet | gap | Outbox/replay cursor not yet in repo. |
| Each local node maintains outbox + replay cursor; publish carries event_id, node_id, idempotency key | [inter-node-data-flow.md#L150-L164](../inter-node-data-flow.md) | required-end-state | [stack/broker/broker_service/](../../../stack/broker/broker_service/) and [stack/sql/broker/001_core.sql](../../../stack/sql/broker/001_core.sql) — outbox table/pattern not confirmed from filenames alone | unverifiable | Needs code-level audit to confirm idempotency shape. |

---

## 7. implementation-roadmap.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Phase 1 (Substrate+Edge): substrate services start reliably | [implementation-roadmap.md#L5-L30](../implementation-roadmap.md) | required-end-state | [docker-compose.substrate.yml](../../../stack/prototype-local/docker-compose.substrate.yml) provides postgres, valkey, minio, clickhouse, langfuse, qdrant, neo4j | partial match | Caddy/cloudflared/Tailscale are Phase 1 "services touched" but absent — expected for prototype-local scope. |
| Phase 1: exposure smoke test exists | [implementation-roadmap.md#L28](../implementation-roadmap.md) | required-end-state | No smoke test script | gap | Same as §3. |
| Phase 2 (Continuity plane): broker API, schema, session/run/artifact registry | [implementation-roadmap.md#L34-L55](../implementation-roadmap.md) | required-end-state | [stack/broker/](../../../stack/broker/) + [stack/sql/broker/001_core.sql](../../../stack/sql/broker/001_core.sql) exist; tests in [stack/broker/tests/test_app.py](../../../stack/broker/tests/test_app.py) | partial match | Artifact registration from media workflows is a known Phase 3 gap (prototype-local-shared-core-plan Gap 3). |
| Phase 3 (OWU + n8n + n8n-mcp + Langfuse wired to broker) | [implementation-roadmap.md#L59-L80](../implementation-roadmap.md) | required-end-state | [test_openwebui_n8n_broker.py](../../../stack/prototype-local/scripts/test_openwebui_n8n_broker.py), [test_n8n_mcp_functional.py](../../../stack/prototype-local/scripts/test_openwebui_n8n_broker.py), both referenced in [gate_shared_core.py](../../../stack/prototype-local/scripts/gate_shared_core.py) | match (prototype level) | Structural trace correlation still unverified. |
| Phase 4 (Hermes gateway + Paperclip through gateway; mock Hermes for CI) | [implementation-roadmap.md#L82-L103](../implementation-roadmap.md) | required-end-state | No in-repo `stack/services/hermes-gateway/` or `paperclip` service | gap | Phase 4 incomplete. |
| Shared-Core Parallelization Gate before node split | [implementation-roadmap.md#L105-L116](../implementation-roadmap.md) | required-end-state | [gate_shared_core.py](../../../stack/prototype-local/scripts/gate_shared_core.py) exists and runs bootstrap+sync+2 tests | partial match | Gate script is real but covers OWU/n8n/n8n-mcp/broker only; does not yet run gateway, memory, canary, restart-resilience tests required by [node-rollout-plan.md#L46-L120](../node-rollout-plan.md). |
| Phase 5 (Honcho/Qdrant/Neo4j/MinIO integrated via continuity plane) | [implementation-roadmap.md#L118-L139](../implementation-roadmap.md) | required-end-state | Qdrant/Neo4j running; no enrichment workers; Honcho service absent | gap | — |
| Phase 6 (hardening, canary, restore drills) | [implementation-roadmap.md#L141-L161](../implementation-roadmap.md) | required-end-state | No canary, restore, or runbook scripts | gap | — |
| Phase 7 (learning plane) | [implementation-roadmap.md#L164-L189](../implementation-roadmap.md) | required-end-state | No learning orchestrator | gap | Expected last. |

---

## 8. deployment-model.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Three layers: shared core, role overlays, node manifests | [deployment-model.md#L16-L23](../deployment-model.md) | intent | Present: [stack/topology/](../../../stack/topology/), [stack/roles/](../../../stack/roles/), [nodes/](../../../nodes/) | match | Structural skeleton in place. |
| Initial role set: `core`, `vps`, `media-cpu`, `media-gpu`, `builder`, `tools` | [deployment-model.md#L56-L63](../deployment-model.md) | current-state | [topology/roles.json](../../../stack/topology/roles.json) declares all six | match | — |
| Role overlay files live in `stack/roles/<role>/docker-compose.role.yml` | [deployment-model.md#L195-L196](../deployment-model.md) | current-state | `stack/roles/core/` and `stack/roles/vps/` are empty dirs; `builder/docker-compose.role.yml` is `services: {}` | drift | `core` and `vps` have no compose fragments (consistent with `compose_files: []`), but `builder` has a compose file that defines no services — either make it meaningful or remove it. |
| Node manifests use `NODE_NAME`, `TARGET`, `ENABLED_ROLES` | [deployment-model.md#L90-L94](../deployment-model.md) | current-state | All three `nodes/*/roles.env.example` match this schema | match | Only `.example` variants exist, not real manifests — flagged in [prototype-local-shared-core-plan.md#L411-L432](../prototype-local-shared-core-plan.md). |
| `./bin/start-1215 nodes`, `show-node vps`, `compose-cmd vps config` work | [deployment-model.md#L189-L195](../deployment-model.md) | current-state | [bin/start-1215.py](../../../bin/start-1215.py) delegates to `uv run --project stack/control start-1215 ...`; [stack/control/control1215/nodes.py](../../../stack/control/control1215/nodes.py) and [compose.py](../../../stack/control/control1215/compose.py) exist | match (structural) | Functional execution not runtime-verified here. |
| Current prototype effectively runs `core + vps + media-cpu + tools` | [deployment-model.md#L224-L230](../deployment-model.md) | current-state | [nodes/vps/roles.env.example](../../../nodes/vps/roles.env.example) sets `ENABLED_ROLES=core,vps,media-cpu,tools` | match | — |

---

## 9. node-roles.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Four node types: VPS hub, Linux prototype, Engineering, Research | [node-roles.md#L18-L25](../node-roles.md) | intent | [nodes/](../../../nodes/) has `vps`, `engineering-pc`, `local-builder` — no research or prototype-specific node folder | drift | `local-builder` is not in node-roles.md; `research` is in doc but not in repo; `Linux prototype` has no dedicated folder (the `vps` node currently *is* the prototype per [deployment-model.md#L224-L230](../deployment-model.md)). |
| No node may self-promote to production | [node-roles.md#L27-L29](../node-roles.md) | policy | No promotion-gate code yet | gap | Phase 7 (learning plane). |
| Engineering node should enable `core, media-gpu, tools` | [node-roles.md#L37-L42](../node-roles.md) | current-state | [nodes/engineering-pc/roles.env.example](../../../nodes/engineering-pc/roles.env.example) = `ENABLED_ROLES=core,media-gpu,tools` | match | — |
| `autoresearch` belongs on research node | [node-roles.md#L193-L215](../node-roles.md) | intent | No research-node folder or `autoresearch` integration in repo | gap / intent | Expected. |

---

## 10. node-rollout-plan.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Parallel node work blocked until shared-core slice is proven | [node-rollout-plan.md#L13-L25](../node-rollout-plan.md) | policy | Gate script covers only OWU/n8n/n8n-mcp/broker path, not gateway/memory/canary/restart | gap | Consistent with doc's own intent; gate tests 1-5 not yet implemented. |
| Gate test 1: Gateway boundary | [node-rollout-plan.md#L50-L62](../node-rollout-plan.md) | required-end-state | No gateway implementation | gap | — |
| Gate test 2: Memory persistence (Honcho write/recall across sessions) | [node-rollout-plan.md#L64-L76](../node-rollout-plan.md) | required-end-state | `setup_hermes_honcho_paperclip.py` runs a memory smoke; not wired into `gate_shared_core.py` | partial | Test exists but is not gated; running it requires host-side Honcho and Hermes. |
| Gate test 3: Fake-secret canary | [node-rollout-plan.md#L78-L94](../node-rollout-plan.md) | required-end-state | No canary script | gap | — |
| Gate test 4: Continuity registration through Paperclip/Hermes | [node-rollout-plan.md#L95-L106](../node-rollout-plan.md) | required-end-state | No paperclip/hermes path | gap | — |
| Gate test 5: Restart resilience | [node-rollout-plan.md#L108-L119](../node-rollout-plan.md) | required-end-state | No restart test script | gap | — |

---

## 11. learning-plane.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| `autoreason` and `hermes-agent-self-evolution` belong in the learning plane, not on request path | [learning-plane.md#L7-L15](../learning-plane.md) | intent | Both are git submodules; neither imported into `stack/` as runtime | match | Intentional adjacency preserved. |
| Components: learning orchestrator, dataset builder, eval runner, autoreason loop, evolution pipeline, candidate registry, promotion gate | [learning-plane.md#L124-L210](../learning-plane.md) | required-end-state | No `stack/learning/` folder | gap | Phase 7. |
| First home for learning plane is the Linux prototype node, not the VPS hub | [learning-plane.md#L340-L361](../learning-plane.md) | intent | No prototype learning wiring yet | gap | Expected. |
| Guardrails: held-out evaluation, no-secret-leak, no-unapproved mutation | [learning-plane.md#L323-L338](../learning-plane.md) | policy | Not implemented | gap | Canary missing (see §5). |

---

## 12. module-env-compilation.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Sources: 7 listed module env files exist | [module-env-compilation.md#L7-L13](../module-env-compilation.md) | current-state | All 7 paths resolve under [modules/](../../../modules/) | match | — |
| `hermes-agent/.env.example` active keys: `TERMINAL_MODAL_IMAGE`, `TERMINAL_TIMEOUT`, `TERMINAL_LIFETIME_SECONDS`, `BROWSERBASE_PROXIES`, `BROWSERBASE_ADVANCED_STEALTH`, `BROWSER_SESSION_TIMEOUT`, `BROWSER_INACTIVITY_TIMEOUT`, `WEB_TOOLS_DEBUG`, `VISION_TOOLS_DEBUG`, `MOA_TOOLS_DEBUG`, `IMAGE_TOOLS_DEBUG` | [module-env-compilation.md#L21-L33](../module-env-compilation.md) | current-state | Grep of [modules/hermes-agent/.env.example](../../../modules/hermes-agent/.env.example) returns exactly these 11 keys uncommented | match | — |
| `honcho/.env.template` active keys include `LOG_LEVEL`, `DB_CONNECTION_URI`, `AUTH_USE_AUTH`, `LLM_OPENAI_COMPATIBLE_BASE_URL`, `LLM_OPENAI_COMPATIBLE_API_KEY`, `LLM_EMBEDDING_PROVIDER`, plus the `DERIVER_*`, `SUMMARY_*`, `DREAM_*`, `VECTOR_STORE_*` keys | [module-env-compilation.md#L42-L58](../module-env-compilation.md) | current-state | All listed keys confirmed active in [modules/honcho/.env.template](../../../modules/honcho/.env.template) | match | — |
| `honcho/.env.template` active keys omit `DIALECTIC_LEVELS__*__PROVIDER` and `DIALECTIC_LEVELS__*__MODEL` | [module-env-compilation.md#L42-L58](../module-env-compilation.md) | current-state | [modules/honcho/.env.template#L129-L149](../../../modules/honcho/.env.template) has 10 uncommented `DIALECTIC_LEVELS__{minimal,low,medium,high,max}__{PROVIDER,MODEL}` lines | drift | Doc list is incomplete; add dialectic keys to the honcho section. |
| `n8n-mcp/.env.example` core keys: `AUTH_TOKEN`, `NODE_DB_PATH`, `NODE_ENV`, `LOG_LEVEL`, `MCP_LOG_LEVEL`, `MCP_MODE`, `PORT`, `HOST`, `REBUILD_ON_START` | [module-env-compilation.md#L155-L163](../module-env-compilation.md) | current-state | Actual uncommented keys in [modules/n8n-mcp/.env.example](../../../modules/n8n-mcp/.env.example): `NODE_DB_PATH`, `MCP_LOG_LEVEL`, `NODE_ENV`, `REBUILD_ON_START`, `MCP_SERVER_PORT`, `MCP_SERVER_HOST`, `MCP_MODE`, `PORT`, `HOST`, `AUTH_TOKEN`, `ENABLE_MULTI_TENANT` | drift | Doc claims `LOG_LEVEL` (not present — only `MCP_LOG_LEVEL`); doc omits `MCP_SERVER_PORT`, `MCP_SERVER_HOST`, `ENABLE_MULTI_TENANT`. |
| `n8n-mcp/.env.docker` values effectively include `HTTP_PORT`, `HTTPS_PORT`, `USE_NGINX` | [module-env-compilation.md#L156-L184](../module-env-compilation.md) | current-state | [.env.docker](../../../modules/n8n-mcp/.env.docker) contains `HTTP_PORT`, `HTTPS_PORT`, `USE_NGINX` | drift | Doc does not list these keys under `.env.docker`. |
| `paperclip/.env.example` keys: `DATABASE_URL`, `PORT`, `SERVE_UI`, `BETTER_AUTH_SECRET` | [module-env-compilation.md#L193-L197](../module-env-compilation.md) | current-state | Exact match in [modules/paperclip/.env.example](../../../modules/paperclip/.env.example) | match | — |
| Keep-populated-now list for `stack/prototype-local/.env` includes `NEO4J_AUTH`, `N8N_MCP_TELEMETRY_DISABLED`, etc. | [module-env-compilation.md#L210-L234](../module-env-compilation.md) | current-state | [.env.example](../../../stack/prototype-local/.env.example) contains all listed keys | match | — |
| Add-now list includes `HONCHO_*`, `PAPERCLIP_*`, `BROKER_APP_PASSWORD`, `LANGFUSE_*`, `BETTER_AUTH_SECRET`, provider API keys | [module-env-compilation.md#L236-L265](../module-env-compilation.md) | current-state | All confirmed in [.env.example#L73-L110](../../../stack/prototype-local/.env.example) | match | — |

---

## 13. prototype-local-shared-core-plan.md

| Claim | Source | Class | Evidence | Status | Note |
|---|---|---|---|---|---|
| Already implemented: substrate compose, broker, OWU pipes, n8n workflows, n8n-mcp, start-1215, control1215 | [prototype-local-shared-core-plan.md#L22-L35](../prototype-local-shared-core-plan.md) | current-state | All cited paths resolve and contain content | match | — |
| Gap 1: `targets.json` claims `prototype-local` includes `paperclip`, `honcho`, `hermes-gateway`, `hermes` | [prototype-local-shared-core-plan.md#L59-L69](../prototype-local-shared-core-plan.md) | current-state (of the time) | [targets.json#L11-L25](../../../stack/topology/targets.json) now lists only 12 services for prototype-local (none of those 4) | drift (doc is stale) | Gap 1 appears **resolved** for `prototype-local` target. However, the `vps-hub` target now claims 15 services including those 4 with an empty `compose_files: []` — the same pattern reappears at the hub level. |
| Gap 2: shared-core gate not implemented (Paperclip→gateway, Honcho memory, canary, restart) | [prototype-local-shared-core-plan.md#L71-L81](../prototype-local-shared-core-plan.md) | current-state | [gate_shared_core.py](../../../stack/prototype-local/scripts/gate_shared_core.py) runs 4 steps, none of which are gateway/memory/canary/restart | match (gap persists) | — |
| Gap 3: media artifacts reach MinIO but not `broker.artifacts` | [prototype-local-shared-core-plan.md#L83-L88](../prototype-local-shared-core-plan.md) | current-state | n8n workflow JSON files under [stack/prototype-local/n8n/](../../../stack/prototype-local/n8n/) include `Generate_Prototype_ComfyUI_SD15_Artifact_Webhook.json` and `Generate_Prototype_Media_Artifact_Webhook.json` (working-tree modified in git status) | unverifiable from static filenames | Node-level inspection of the workflow JSON would confirm whether artifact rows are now written. Broker schema has `artifacts` but registration path not confirmed here. |
| Gap 4: n8n-mcp not yet in prototype gate | [prototype-local-shared-core-plan.md#L90-L94](../prototype-local-shared-core-plan.md) | current-state (of the time) | [gate_shared_core.py#L45](../../../stack/prototype-local/scripts/gate_shared_core.py) calls `test_n8n_mcp_functional.py` | drift (doc is stale) | Gap 4 is **resolved**; doc should be updated to reflect that n8n-mcp is now gated. |
| Gap 5: `.env` committed and must be rotated | [prototype-local-shared-core-plan.md#L96-L98](../prototype-local-shared-core-plan.md) | current-state (of the time) | `.env` is in [.gitignore#L15](../../../.gitignore); `git ls-files` shows it is not tracked | drift (doc is stale) | Gap 5 is **resolved**; doc should be updated. Secret rotation outside git history still recommended. |
| Phase 1 task: remove committed `.env`, rotate secrets | [prototype-local-shared-core-plan.md#L137-L159](../prototype-local-shared-core-plan.md) | required-end-state | Covered above; rotation status cannot be verified from artifacts | partially resolved | — |
| Phase 1 task: pin image versions for OWU, n8n, n8n-mcp, ComfyUI | [prototype-local-shared-core-plan.md#L143-L147](../prototype-local-shared-core-plan.md) | required-end-state | Compose: open-webui SHA-digest-pinned, comfyui SHA-digest-pinned, `n8n` image arg `n8nio/n8n:2.3.6`, `n8n-mcp` `ghcr.io/czlonkowski/n8n-mcp:2.33.5` | match | All four pinned. |
| Phase 1 task: other images pinned | derived from review-01 §4 | required-end-state | `postgres:17` pinned; `neo4j:latest`, `minio/minio`, `qdrant/qdrant`, `clickhouse/clickhouse-server`, `busybox:1.36` (pinned), `valkey/valkey:8-alpine` (pinned), `minio/mc` unpinned | partial | Unpinned: `neo4j`, `minio`, `qdrant`, `clickhouse`, `minio/mc`. |
| Phase 4 task: move n8n-mcp from optional to required; add functional tests | [prototype-local-shared-core-plan.md#L220-L245](../prototype-local-shared-core-plan.md) | required-end-state | [test_n8n_mcp_functional.py](../../../stack/prototype-local/scripts/test_n8n_mcp_functional.py) exists and is wired into gate | match | Depth of functional coverage not verified here. |
| Phase 5 task: repo-owned Honcho compose wiring under `stack/` | [prototype-local-shared-core-plan.md#L254-L273](../prototype-local-shared-core-plan.md) | required-end-state | No `honcho` service in compose; env placeholders only | gap | — |
| Phase 6 task: Hermes gateway under `stack/services/hermes-gateway/` | [prototype-local-shared-core-plan.md#L280-L296](../prototype-local-shared-core-plan.md) | required-end-state | No such path | gap | — |
| Phase 7 task: `paperclip-orchestrator` image | [prototype-local-shared-core-plan.md#L300-L325](../prototype-local-shared-core-plan.md) | required-end-state | Not in repo | gap | — |
| Phase 9 task: 10-test E2E harness | [prototype-local-shared-core-plan.md#L359-L409](../prototype-local-shared-core-plan.md) | required-end-state | 4 of 10 covered via `gate_shared_core.py` step chain; tests `paperclip_gateway_roundtrip`, `honcho_memory`, `fake_secret_canary`, `restart_resilience` not present | partial | 6/10 still missing. |
| Phase 10 task: create a real node manifest for this box | [prototype-local-shared-core-plan.md#L411-L432](../prototype-local-shared-core-plan.md) | required-end-state | Only `nodes/*/roles.env.example` exist (no real `.env`/manifest) | gap | — |

---

## 14. review-01.md (prior review; unresolved recommendations)

| Recommendation | Source | Evidence | Status | Note |
|---|---|---|---|---|
| Automate certs with Caddy ACME (avoid CF origin cert lock-in) | [review-01.md#L27](../review-01.md) | No Caddy service yet | gap | Phase 1. |
| Ship one-shot exposure smoke test that crawls port map | [review-01.md#L28, L89](../review-01.md) | Not present | gap | — |
| Unit tests against broker schema for idempotency keys/unique constraints | [review-01.md#L31](../review-01.md) | [stack/broker/tests/test_app.py](../../../stack/broker/tests/test_app.py) exists | unverifiable | Test depth not audited here. |
| Mock Hermes for CI | [review-01.md#L36](../review-01.md) | None in repo | gap | — |
| `n8n-MCP` version pinning | [review-01.md#L48-L49](../review-01.md) | `ghcr.io/czlonkowski/n8n-mcp:2.33.5` pinned | match | — |
| Fake-secret canary in git hooks | [review-01.md#L85-L86](../review-01.md) | No `.git/hooks/*` or `.pre-commit-config.yaml` evidence | gap | — |
| Automated restore drills | [review-01.md#L42](../review-01.md) | None | gap | — |
| DR playbook (WAL shipping, MinIO replication, n8n JSON export, Langfuse Parquet export) | [review-01.md#L59-L67](../review-01.md) | None | gap | — |
| Observability dashboard / Grafana Prometheus exporters | [review-01.md#L69-L74](../review-01.md) | None | gap | — |
| Schema governance: use lookup table for `event_kind` (not Postgres enum); `payload_version` integer | [review-01.md#L75-L79](../review-01.md) | Needs inspection of [stack/sql/broker/001_core.sql](../../../stack/sql/broker/001_core.sql) | unverifiable | — |
| Tailscale ACL limiting `paperclip:3100` to `tag:ops` | [review-01.md#L82](../review-01.md) | No Tailscale config yet | gap | — |
| Neo4j & Qdrant disabled by default via `COMPOSE_PROFILES=graph,vector` | [review-01.md#L84](../review-01.md) | Both services currently unconditional in compose (no profile) | policy-violation (soft) | Consider moving behind profiles per review. |
| Doppler or equivalent for CI secret handling | [review-01.md#L85](../review-01.md) | No CI config (`.github/` absent) | gap | — |
| Pin container tags to explicit versions (not `latest`) | [review-01.md#L91](../review-01.md) | 5 images unpinned (neo4j, minio, qdrant, clickhouse, mc) | partial | — |

---

## Cross-doc summary of drift patterns

1. **Doc-lags-repo drift** (doc still claims a problem that has been fixed): [prototype-local-shared-core-plan.md](../prototype-local-shared-core-plan.md) Gap 1 (for prototype target), Gap 4, and Gap 5 are no longer accurate. The shared-core plan should be updated or rewritten post-progress.
2. **Doc-leads-repo drift** (doc asserts current state but repo is behind): [network-port-map.md](../network-port-map.md) does not reflect `n8n-mcp` host bind `127.0.0.1:13000` or ComfyUI `:8188`; missing broker port `:8090`.
3. **Gap-by-design** (acceptable phase gaps): absence of Paperclip, Hermes gateway, Honcho runtime, Caddy, cloudflared, Tailscale, learning plane, approval workflows, enrichment workers, restore drills, observability dashboards.
4. **Node-model drift**: docs name `Engineering`, `Research`, `Linux prototype` nodes; repo has `vps`, `engineering-pc`, `local-builder`. Reconcile naming.
5. **Policy→implementation gaps**: exposure smoke test, fake-secret canary, restart-resilience test, restore drills are all referenced by ≥2 docs and by the gate plan but not yet implemented.
6. **Port/config triangle**: Paperclip port disagreement — [network-port-map.md](../network-port-map.md) says `:3100`, [.env.example](../../../stack/prototype-local/.env.example) says `:8484`. One source of truth needed before Phase 7 implementation.
