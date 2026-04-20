# 1215-VPS Service Catalog

This catalog defines every service considered for the architecture, its role, and whether it is required in v1.

Exposure levels:

- `Public` means internet-reachable through Cloudflare Access and Caddy
- `Tailnet-only` means reachable only through Tailscale plus Caddy
- `Internal-only` means Docker or host-internal only
- `Host-only` means no network exposure; access is filesystem or local process only

## Required in v1

| Service | Layer | Role | Depends On | Persistence | Exposure | Rationale |
|---|---|---|---|---|---|---|
| `Caddy` | Edge | Central ingress router | Cloudflare, Tailscale | config + cert state | Public and Tailnet-only | Single ingress point simplifies exposure policy |
| `cloudflared` | Edge | Public tunnel to selected apps | Cloudflare | host service state | Public path only | Required for clientless access to approved public apps |
| `Tailscale` | Edge | Private operator/admin access | host networking | host state | Tailnet-only path | Required for trusted admin surfaces |
| `Open WebUI` | Surface | Primary human-facing shell | Caddy, n8n, broker | app data | Public | Main interaction surface for users and operators |
| `Paperclip` | Surface | Specialist orchestration workbench | Hermes gateway, broker | app data + workspaces | Tailnet-only | Purpose-built company and orchestration surface |
| `n8n` | Nervous system | Workflow automation, approvals, scheduling | DB, object store, broker | n8n data | Public or Tailnet-only | Trusted control and policy layer; final exposure decided after prototype validation |
| `n8n-mcp` | Nervous system | Structured access to `n8n` docs/capabilities | n8n | app state if needed | Internal-only | Agent-facing control surface for workflow intelligence |
| `Broker API / workers` | Continuity | Canonical event and continuity plane | Postgres | broker tables | Internal-only | Core system of record |
| `Postgres / Supabase DB` | Core data | Durable relational store | storage | database volumes | Internal-only | Hosts broker schema and Honcho DB |
| `Valkey / Redis` | Core data | Cache / queue support | storage | data volume | Internal-only | Supports Honcho and selected workflows |
| `MinIO` | Retrieval / artifacts | Canonical artifact and object store | storage | object volume | Internal S3, Tailnet console | Needed for artifact lineage and binary outputs |
| `Qdrant` | Retrieval | Semantic retrieval plane | storage | vector volume | Tailnet-only or Internal-only | Purpose-built semantic recall layer |
| `Neo4j` | Retrieval | Fact and relationship graph | storage | graph volume | Tailnet-only or Internal-only | Purpose-built relationship and entity layer |
| `Honcho` | Memory | Shared-memory provider | Postgres, Redis | DB-backed | Internal-only | VPS memory provider behind adapter boundary |
| `Langfuse` | Observability | Tracing and lineage UI / workers | ClickHouse, MinIO, Redis, Postgres | DB + object state | Tailnet-only | First-class observability from day one |
| `ClickHouse` | Core data | Langfuse analytics store | storage | data volume | Internal-only | Required by Langfuse architecture |
| `Hermes gateway` | Host execution | Container-to-host execution boundary | Hermes host install | host state | Host-only | Clean execution boundary for Paperclip and later tools |
| `Hermes` | Host execution | Actual agent runtime | profiles, Honcho | profile/workspace state | Host-only | Required for Hermes-backed orchestration |

## Optional but Retained

These services remain part of the candidate rich stack but must justify their operational cost during implementation.

| Service | Layer | Role | Depends On | Persistence | Exposure | Keep Condition |
|---|---|---|---|---|---|---|
| `SearXNG` | Surface / retrieval | Search backend for tools or workflows | network egress | config volume | Tailnet-only | Keep if Open WebUI or `n8n` uses controlled web search |
| `Flowise` | Surface | Prompt / graph prototyping surface | optional model services | app volume | Tailnet-only | Keep only if it fills a real gap not covered by Open WebUI + n8n + Paperclip |
| `Ollama` | Model runtime | Local model hosting | compute / GPU if used | model volume | Tailnet-only or Internal-only | Keep if local inference is part of v1 rather than future experimentation |
| `Supabase Studio` | Admin surface | DB/admin convenience UI | Supabase services | DB state | Tailnet-only | Keep if it materially improves ops without expanding risk |
| `Learning orchestrator` | Learning plane | Schedules and coordinates offline self-improvement jobs | broker, Langfuse, candidate registry | run history + config | Internal-only | Keep if self-improvement is part of the node pattern rather than a manual side process |
| `Eval runner` | Learning plane | Replays tasks and runs benchmark suites in a sandbox | learning orchestrator, Hermes mocks or sandbox runtimes | ephemeral + reports | Internal-only | Keep if candidate evaluation is automated and repeatable |
| `Candidate registry / promotion gate` | Learning plane | Stores candidate variants, scores, approvals, and rollout state | broker, MinIO, Postgres | DB + artifact state | Tailnet-only or Internal-only | Keep if learning outputs are promoted through explicit governance |

## Deferred Beyond v1

| Service / Concern | Reason for Deferral |
|---|---|
| Engineering-host live integration | Not needed for VPS-complete milestone |
| Research-host live integration | Not needed for VPS-complete milestone |
| Remote provider sync jobs | Defer until VPS contracts stabilize |
| Additional public apps | Public surface is intentionally constrained to two apps |
| Broad MCP self-management for all services | Useful later, but not needed before core contracts and guardrails are stable |

## Service-to-Role Fit Notes

### Open WebUI
This remains the primary shell because it best fits broad human interaction, chat, tool use, and retrieval workflows.

### Paperclip
This is retained because it is unusually strong at orchestration, company runtime, and long-lived multi-agent operations. It should not become the primary shell.

### n8n
This is promoted, not demoted. It is most valuable when used as a policy-aware workflow nervous system rather than a side utility.

The unresolved question is exposure, not importance:

- safer default: tailnet-only UI and admin surface
- higher-convenience option: public through Cloudflare Access
- if public webhooks remain necessary, they should ideally be narrower than exposing the full `n8n` surface

### Qdrant and Neo4j
Both stay in v1, but they must not mirror the same information blindly:

- `Qdrant` holds semantic representations
- `Neo4j` holds structured relationships and facts

### Langfuse
This is first-class because the system needs auditable lineage from day one, not just logs after the fact.

### Learning Plane Components
The self-improvement modules are not modeled as primary apps because their role
is different:

- they consume traces, broker records, and benchmark data
- they generate candidate improvements offline
- they require evaluation and rollback-friendly comparison
- they should not mutate live behavior directly on the request path

That makes them learning-plane components, not substrate or surface services.
