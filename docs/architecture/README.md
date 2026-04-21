# 1215-VPS Architecture Docs

This folder contains the architectural documents for `1215-vps`. Three of
them are canonical; the rest are either supporting references or historical
context.

## Canonical

Read these first. Each is self-contained.

- **[north-star.md](north-star.md)** — authoritative target. What this
  prototype becomes when complete.
- **[current-state.md](current-state.md)** — factual snapshot of what is
  actually in the repo right now.
- **[roadmap.md](roadmap.md)** — ordered phases to get from current state
  to the north star.

## Supporting References

Detailed specifications that expand on specific aspects of the north star:

- [service-catalog.md](service-catalog.md) — per-service roles, requirements,
  dependencies, persistence, exposure
- [network-port-map.md](network-port-map.md) — network zones, port
  assignments, exposure policies
- [deployment-model.md](deployment-model.md) — shared core, role overlays,
  node manifests
- [node-roles.md](node-roles.md) — VPS / prototype / engineering / research
  node differentiation
- [runtime-flows.md](runtime-flows.md) — execution paths and sequence
  diagrams
- [inter-node-data-flow.md](inter-node-data-flow.md) — cross-node publish /
  consume patterns (deferred)
- [learning-plane.md](learning-plane.md) — observation, evaluation,
  promotion (deferred)
- [security-observability.md](security-observability.md) — non-functional
  constraints
- [module-env-compilation.md](module-env-compilation.md) — env variables
  per module
- [implementation-roadmap.md](implementation-roadmap.md) — earlier,
  higher-level phase outline (superseded for this prototype by
  `roadmap.md`)
- [prototype-local-shared-core-plan.md](prototype-local-shared-core-plan.md)
  — prior implementation plan for the Linux prototype
- [node-rollout-plan.md](node-rollout-plan.md) — multi-node rollout
  sequencing

## Historical / Legacy

Kept for reference; superseded by the canonical set:

- [overview.md](overview.md) — original north-star-style doc; superseded
  by [north-star.md](north-star.md)
- [review-01.md](review-01.md) — earlier architectural review
- [Self-Hosted Long-Horizon Memory Architecture for Three Hermes-Backed.md](Self-Hosted%20Long-Horizon%20Memory%20Architecture%20for%20Three%20Hermes-Backed.md)
  — original architectural vision document

## Audit Outputs

Historical audit artifacts from a prior drift analysis:

- [audit/README.md](audit/README.md)
- [audit/drift-matrix.md](audit/drift-matrix.md)
- [audit/claims-index.json](audit/claims-index.json)
