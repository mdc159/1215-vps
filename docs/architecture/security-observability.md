# 1215-VPS Security and Observability

This document captures the non-functional constraints that the implementation must preserve.

## Exposure Rules

### Public
- `Open WebUI`
- `n8n` only if prototype validation confirms that public operator access is worth the additional risk

Both public apps must be protected by:

- Cloudflare Tunnel
- Cloudflare Access
- Caddy hostname routing
- each app's own application auth where applicable

If `n8n` remains public, hardening requirements include:

- no credential-less workflow execution paths
- Cloudflare Access enforcement
- rate limiting
- explicit review of any webhook endpoints that bypass the UI

### Tailnet-only
- `Paperclip`
- `Langfuse`
- `MinIO console`
- `Qdrant`
- `Neo4j`
- optional retained admin tools

### Internal-only
- `Postgres / Supabase DB`
- `Valkey`
- `MinIO S3 API`
- `ClickHouse`
- `Honcho`
- `n8n-mcp`
- broker internal APIs and workers

### Host-only
- Hermes gateway Unix socket
- Hermes binary
- Hermes profile and workspace directories

## Secret Handling Rules

- No secrets are committed into the repo.
- No secrets are placed into Hermes memory or Honcho memory intentionally.
- No secrets are persisted into Langfuse traces intentionally.
- No secrets are embedded into graph or vector stores intentionally.
- Root environment contract remains the single source of truth for service secrets.
- Any service that needs a derived or translated env shape receives a rendered subset, not hand-maintained duplicate secret files.

## Approval Boundaries

Sensitive workflows must fail closed and require explicit approval. Sensitive classes include at minimum:

- destructive data mutation
- identity or access control changes
- environment and secret changes
- public exposure changes
- code or config deployment actions

Approval records must include:

- requester surface
- requested action
- approval outcome
- approver identity when human-in-the-loop applies
- correlated run and trace identifiers

## Fake-Secret Canary Policy

Use a deterministic fake secret during validation, such as:

- `sk-test-DO-NOT-STORE-12345`

The canary must not persist in:

- Hermes memory
- Honcho memory
- Langfuse traces
- `n8n` workflow state beyond bounded test evidence
- `Qdrant`
- `Neo4j`
- `MinIO` artifacts except tightly scoped test fixtures if created intentionally
- project docs or source files

The canary test is a required acceptance check for the integrated system.

## Trace and Lineage Rules

Langfuse is first-class in v1. Correlation identifiers must tie together:

- user request
- workflow run
- broker event
- Hermes execution
- Paperclip task or heartbeat
- artifact registration
- memory write or recall when surfaced

Every meaningful action should be traceable from:

1. entrypoint
2. orchestration step
3. continuity record
4. produced artifact or side effect

Workflow-to-trace mapping must be enforced by implementation, not by convention alone. `workflow_id`, `run_id`, and trace correlation identifiers must survive across `n8n`, broker records, Hermes execution, and artifact registration.

## Continuity Plane Governance

The broker and event tables are treated as immutable append-only records.

Required governance rules:

- event writes must be idempotent
- event payloads must be versioned
- enrichment and publication writes must carry a source-event hash or equivalent immutable linkage
- retries must not rewrite historical event meaning
- lookup tables are preferred over hard Postgres enums where event vocabularies are likely to evolve

Recommended implementation rules:

- use explicit unique constraints for event identity and idempotency keys
- prefer conflict-safe inserts over update-in-place semantics for event records
- keep schema migration tooling under version control and require forward and rollback review for broker schema changes

## Logging and Failure Visibility

At minimum, the system must make these failures legible:

- failed workflow execution
- broker publish failure
- artifact registration failure
- Hermes gateway failure
- Paperclip execution failure
- Honcho memory write or recall failure
- enrichment failures into Qdrant or Neo4j

Failures should be:

- visible in traces
- written into broker state where relevant
- recoverable or replayable where appropriate

## Rollback and Recovery Expectations

The architecture should support rollback at these boundaries:

- service deployment rollback
- workflow definition rollback
- broker worker replay after partial failure
- approval flow retry or expiration handling
- enrichment retry without duplicating continuity state

Recovery rules:

- continuity records are append-only
- retries must be idempotent where possible
- partial failures must not leave silent drift between broker, artifacts, and retrieval stores

Minimum recovery practices:

- nightly logical backup of continuity data to an off-box location
- off-box replication or export path for MinIO artifacts
- restore drills against a blank environment
- verification that restored continuity data preserves event lineage rather than mutating historical identities in place
