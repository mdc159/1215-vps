# 1215-VPS Implementation Roadmap

This roadmap translates the approved architecture into build order. It is intentionally phase-oriented rather than file-oriented.

## Phase 1: Substrate and Edge

**Objective**
- Establish the selected substrate services and ingress model without yet wiring higher-level continuity behavior

**Services touched**
- Caddy
- cloudflared
- Tailscale
- Postgres / Supabase DB
- Valkey
- MinIO
- ClickHouse
- Langfuse base services
- Qdrant
- Neo4j
- optional retained services only if justified

**Acceptance criteria**
- selected services start reliably
- persistence survives restart
- public and tailnet hostname routing are correct
- no private data service is publicly exposed
- exposure smoke test exists and can fail the build on unexpected external reachability

**Main risks**
- upstream bundle assumptions leaking into the repo-owned topology
- accidental overexposure during bootstrap

## Phase 2: Shared Continuity Plane

**Objective**
- Build the system of record before wiring high-level surfaces deeply into it

**Services touched**
- broker schema inside Postgres
- broker API / workers
- artifact registry
- session and run registry
- provider checkpoint model
- inter-node publish and replay contracts

**Acceptance criteria**
- append-only event publication works
- replay and query paths exist
- artifacts are registered durably
- checkpoints survive restart and partial failure
- local-node outbox and replay assumptions are documented well enough to prototype
- schema tests cover idempotency keys, append-only semantics, and payload version expectations

**Main risks**
- continuity logic being bypassed by direct service-to-service writes
- schema design drifting into provider-specific assumptions

## Phase 3: Primary Human and Workflow Surfaces

**Objective**
- Integrate Open WebUI and `n8n` against the continuity plane and tracing layer

**Services touched**
- Open WebUI
- n8n
- n8n-mcp
- Langfuse
- broker API / workers

**Acceptance criteria**
- Open WebUI can invoke approved `n8n` capabilities
- workflow execution is trace-correlated
- user interactions produce continuity records
- approvals and workflow outcomes are auditable
- `n8n` trace correlation is enforced structurally, not by operator convention

**Main risks**
- webhook spaghetti instead of stable tool and workflow contracts
- inconsistent correlation IDs between surfaces

## Phase 4: Host Execution and Specialist Orchestration

**Objective**
- Add the Hermes execution boundary and the Paperclip specialist surface

**Services touched**
- Hermes gateway
- Hermes host install
- Paperclip
- broker API / workers
- Langfuse

**Acceptance criteria**
- Paperclip can reach Hermes only through the gateway
- session resume and workspace semantics work
- execution outputs and artifacts register correctly
- no direct host execution path bypasses the gateway
- CI can exercise Paperclip integration against a mock Hermes implementation without requiring the host binary

**Main risks**
- container-to-host coupling expanding beyond the gateway
- unclear ownership of workspace and profile state

## Phase 5: Memory and Retrieval Integrations

**Objective**
- Connect Honcho, Qdrant, Neo4j, and MinIO through the continuity plane rather than through ad hoc side writes

**Services touched**
- Honcho
- Qdrant
- Neo4j
- MinIO
- broker API / workers

**Acceptance criteria**
- Honcho operates behind an adapter boundary
- memory events and recalls produce traceable continuity artifacts
- Qdrant and Neo4j each receive purpose-fit data
- artifact storage and retrieval are linked in the registry
- a canonical enrichment path exists before enrichment work is split across multiple workers

**Main risks**
- duplicate or meaningless mirroring into graph and vector stores
- memory behavior leaking provider-specific assumptions into the core contracts

## Phase 6: Optional Retained Services and Hardening

**Objective**
- Add only the retained optional services that still justify their operational cost, then finish hardening and runbooks

**Services touched**
- Flowise if retained
- SearXNG if retained
- Ollama if retained
- security and observability glue
- operator CLI and runbooks

**Acceptance criteria**
- retained optional services have clear architectural roles
- no unresolved exposure drift exists
- observability, rollback, and recovery documentation are complete
- fake-secret canary tests pass across all active subsystems
- restore drills and backup verification are documented as operational requirements

**Main risks**
- optional tools creeping back into the stack without purpose
- hardening left until too late

## VPS-Complete Done Bar

The VPS architecture is considered complete when:

- the selected substrate is stable
- the continuity plane is the canonical shared contract
- Open WebUI and `n8n` are integrated and observable
- Paperclip and Hermes operate through the intended boundary
- Honcho, Qdrant, Neo4j, MinIO, and Langfuse are integrated through explicit contracts
- exposure policy is enforced exactly as designed
- the system can be operated and debugged through documented runbooks
