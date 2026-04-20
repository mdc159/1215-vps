# 1215-VPS Node Roles

This document defines the role of each node type in the broader system.

The purpose is to keep the architecture from collapsing into "every machine does
everything." Different nodes are allowed to optimize for different things:

- the VPS hub optimizes for stability, continuity, and shared services
- the local prototype optimizes for proving the node pattern safely
- the engineering node optimizes for applied build and execution work
- the research node optimizes for exploration and autonomous experimentation

## Node Types

| Node | Primary job | Risk posture | May promote directly? |
|---|---|---|---|
| `VPS hub` | Shared continuity and operational backbone | Conservative | No |
| `Linux prototype` | First implementation of the local-node pattern | Moderate | No |
| `Engineering node` | Applied engineering execution and tooling | Moderate | No |
| `Research / experimental node` | Autonomous search, exploration, and candidate generation | High | No |

The last column is intentional. Nodes may generate candidates, but promotion
into shared live behavior must flow through the promotion gate.

## 1. VPS Hub

The VPS hub is the canonical shared system.

It owns:

- continuity plane
- shared broker events
- shared artifact registry
- workflow nervous system
- observability and lineage
- shared memory integration
- promotion records

It should optimize for:

- uptime
- auditability
- replay correctness
- controlled exposure
- predictable operations

It should not be the primary place for:

- aggressive autonomous mutation
- unconstrained prompt experimentation
- high-churn eval loops

### Allowed behavior

- register candidate artifacts
- store evaluation records
- host promotion decisions
- run bounded evaluation jobs if needed

### Forbidden default behavior

- direct self-modification of live runtime behavior
- unreviewed production mutation from learning jobs
- direct peer-mesh control behavior across nodes

## 2. Linux Prototype Node

The Linux prototype node is the first concrete implementation of the local-node
pattern.

It exists to prove:

- the local substrate layout
- Hermes boundary behavior
- replay and outbox assumptions
- learning-plane integration
- candidate evaluation and rollback mechanics

It should be the first place new node-level patterns are tested before they are
generalized to other local nodes.

### Allowed behavior

- run the same core contracts as the VPS hub
- test candidate workflows and evaluation jobs
- exercise bounded autonomous loops
- publish validated candidate artifacts to the hub

### Forbidden default behavior

- bypassing broker contracts
- becoming an ad hoc second hub
- directly coordinating with other local nodes as a normal path

## 3. Engineering Node

The engineering node is optimized for build, debugging, and implementation
workloads.

It should specialize in:

- Hermes-backed engineering tasks
- local workspaces and repositories
- artifact generation for code and docs
- bounded replay of relevant continuity and task context

It should publish:

- execution summaries
- build artifacts and reports
- approved engineering knowledge
- benchmark and failure data relevant to the shared system

It should keep local:

- machine-specific workspaces
- transient build state
- local caches
- credentials and private execution details

### Allowed behavior

- consume shared continuity state from the hub
- publish outputs and artifacts back to the hub
- participate in evaluation runs relevant to engineering tasks

### Forbidden default behavior

- direct production mutation without promotion controls
- direct node-to-node coordination as a normal control path

## 4. Research / Experimental Node

The research node is the right home for aggressive autonomous experimentation.

This is where `autoresearch` fits best.

Why:

- it assumes repeated autonomous mutation
- it works well in constrained experimental loops
- it optimizes for exploration velocity over runtime stability
- it benefits from isolation from the live production path

In this architecture, the research node is the place for:

- broad prompt and strategy search
- benchmark-driven iteration
- experimental agent org structures
- `autoresearch`-style overnight loops
- high-churn candidate generation

### Allowed behavior

- autonomous mutation of experimental code and prompts
- local benchmark loops
- speculative search over strategy space
- generation of candidate artifacts, reports, and benchmark results

### Required outputs to the hub

- candidate artifacts
- experiment summaries
- benchmark metrics
- trace and lineage references
- optionally distilled findings or design recommendations

### Forbidden default behavior

- direct promotion into shared production behavior
- direct mutation of VPS hub configuration
- direct mutation of shared memory, workflow policy, or broker semantics

## Research Node and `autoresearch`

Karpathy's `autoresearch` is a strong fit for the research node because it is
fundamentally:

- a discovery engine
- a mutation-and-evaluate loop
- a research sandbox

It is not a good default fit for the VPS hub because the hub must remain:

- stable
- shared
- auditable
- rollback-friendly

So the architecture should treat `autoresearch` as:

- **first-class on the research node**
- **candidate-producing, not self-promoting**

That keeps the system ambitious without making the shared runtime reckless.

## Promotion Model Across Nodes

All nodes follow the same promotion rule:

1. generate candidate
2. evaluate candidate
3. publish candidate and metrics
4. review or policy-gate candidate
5. canary or staged rollout
6. adopt more broadly if it holds

This applies even to the research node. The difference is not whether it can
generate candidates; the difference is how aggressive its search space is.

## Node-to-Node Policy

Default system policy remains hub-and-spoke:

- node -> hub: normal
- hub -> node: normal
- node -> node: exceptional

This matters most for the research node. It may be noisy, but it should still
publish through the hub unless a later explicit exception is designed.

## Acceptance Criteria

The node-role model is ready when:

- each node type has a distinct optimization goal
- the research node has a clear place for `autoresearch`
- no node is implicitly allowed to self-promote into production
- publish, replay, and promotion responsibilities are clear
- local experimentation and shared runtime governance are clearly separated
