# 1215-VPS Node Rollout Plan

This plan turns the node model into an execution order.

The main constraint is deliberate:

- do not split into parallel node-specific implementation tracks yet
- first complete the minimum shared-core gate

That gate exists to prevent us from debugging three node variants before the
host-execution and memory seams are proven once.

## Split Gate

Parallel node work is blocked until the following minimum shared-core slice is
implemented and tested on the prototype substrate:

1. Paperclip is reachable in the stack
2. Hermes is reachable only through the intended gateway boundary
3. Honcho is installed privately and reachable from the Hermes side
4. broker, artifact, and trace registration still work across that path
5. the end-to-end tests below pass

Until then, the repo may continue to add documents, manifests, and deployment
controls, but it should not fan out into serious per-node feature work.

## Minimum Shared-Core Gate

### Scope

The minimum shared-core gate is not "all of Paperclip" or "all of Honcho."
It is the smallest slice that proves:

- host execution has a clean boundary
- memory has a clean boundary
- both fit the same continuity and artifact model as the rest of the stack

### Required surfaces

- Paperclip
- Hermes gateway
- Hermes runtime boundary
- Honcho memory service
- broker continuity plane
- MinIO artifact path
- Langfuse tracing where applicable

### Required tests

#### Gate test 1: Gateway boundary

Prove:

- Paperclip cannot bypass the gateway
- Hermes calls succeed through the gateway
- failure at the gateway is visible and bounded

Evidence:

- gateway health check
- mocked or real Hermes invocation through the gateway
- no alternate direct host path in compose/runtime wiring

#### Gate test 2: Memory persistence

Prove:

- Honcho is private
- Hermes can write and recall a harmless durable fact through the intended path
- the fact survives a fresh session

Evidence:

- Honcho health check
- Hermes memory status
- cross-session recall test

#### Gate test 3: Fake-secret canary

Prove:

- a fake secret does not leak into durable memory or logs

Evidence:

- fake secret submitted as a canary
- explicit negative checks in:
  - Hermes memory
  - Honcho logs
  - Langfuse traces
  - broker events
  - `n8n` notes/workflow state if touched
  - repo files

#### Gate test 4: Continuity registration

Prove:

- a Paperclip/Hermes-backed execution can still register node/session/run/event
  state and artifact links correctly

Evidence:

- broker event creation
- artifact registration if a file is produced
- trace correlation where applicable

#### Gate test 5: Restart resilience

Prove:

- after restart, the minimum path still functions without manual repair

Evidence:

- compose restart
- gateway still reachable
- Honcho still reachable
- recall still works

## Decision Point After the Gate

Passing the shared-core gate does **not** automatically mean the repo should
split into parallel node tracks.

It means we finally have enough evidence to decide responsibly between:

- continue deepening the single prototype stack
- begin a limited node split
- do a hybrid, where only one node-specific track begins and the rest wait

That decision should be made after reviewing:

- gateway reliability
- Honcho memory behavior
- fake-secret canary results
- continuity correctness through the host-execution path
- restart resilience

## Candidate Node Plans After the Gate

These are candidate tracks that become eligible for consideration only after the
shared-core gate passes and a deliberate review says the split is justified.

### VPS Node

Primary work:

- ingress hardening
- public vs tailnet exposure decisions
- operator runbooks
- backup and restore drills
- production-safe observability

Primary tests:

- exposure smoke test
- backup and restore verification
- operator recovery checklist

### Engineering / Media Node

Primary work:

- GPU-backed media role
- ComfyUI model/runtime tuning
- image/video workflow library
- artifact publication back to VPS

Primary tests:

- GPU media health
- workflow queue/poll/download
- MinIO artifact registration
- broker continuity for media outputs

### Local Builder Node

Primary work:

- page-builder workflows
- asset consumption from MinIO
- site/package assembly
- verification and deployment helpers

Primary tests:

- artifact-to-page build path
- output verification
- builder role isolation from media-specific assumptions

## Recommended Execution Order

1. minimum shared-core gate
2. explicit post-gate review and decision
3. only then, if justified:
   - VPS hardening and operator path
   - engineering/media node path
   - local builder path
4. research or autonomous node path later

This keeps the shared contract stable before higher-variance workloads are
introduced and prevents the plan from assuming that splitting is always the
right next move.

## Archon Task Shape

The work should be tracked in these groups:

- `shared-core-gate`
- `post-gate-review`
- candidate node tracks only if the review says to proceed

Do not treat node-specific work as committed implementation just because the
tasks exist. The gate exists precisely so we can stop and decide.

## Done Bar For Parallelization

Parallel node implementation is allowed when all of the following are true:

- Paperclip is wired into the prototype stack
- Hermes is reachable only through the intended gateway boundary
- Honcho memory works and is private
- the fake-secret canary test passes
- continuity registration still works through the host-execution path
- restart resilience is proven once on the prototype substrate

That is the point where the common substrate is stable enough to support node
specialization without multiplying uncertainty.
