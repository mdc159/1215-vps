# 1215-VPS Deployment Model

This document defines how the same repo should support the VPS and future local
nodes without turning into "one branch per machine" or "every machine runs
everything."

The key rule is simple:

- shared contracts live once
- capabilities are enabled by role overlays
- each physical node selects roles through a small local manifest

That lets lower-level core updates propagate everywhere while machine-specific
tools remain opt-in.

## Layers

The repo should be treated as three layers:

1. shared core
2. role overlays
3. node manifests

### 1. Shared core

The shared core is the lowest common denominator. It is not "all services on all
machines." It is the set of contracts and conventions that every node must
understand.

The shared core includes:

- broker event and continuity semantics
- artifact layout and MinIO conventions
- workflow payload shapes
- environment variable naming conventions
- healthcheck and verification routines
- service naming and compose conventions
- shared docs, runbooks, and recovery procedures

Examples:

- an artifact event should look the same whether it came from the VPS or a local
  node
- `objectKey`, `promptId`, `sessionId`, and workflow version metadata should
  retain the same meaning everywhere
- the same repo-owned `n8n` or Open WebUI artifact should not need per-node
  forks just to move between machines

### 2. Role overlays

Role overlays enable capabilities. They are the place where we decide which
services and workflows belong together for a class of nodes.

Initial role set:

| Role | Purpose | Typical services |
|---|---|---|
| `core` | continuity, artifacts, standard contracts | broker, Postgres, MinIO, baseline shared services |
| `vps` | user-facing hub and orchestration | Open WebUI, `n8n`, Langfuse, ingress-facing services |
| `media-cpu` | smoke-test generation and CPU fallback | ComfyUI in CPU mode, lightweight media workflows |
| `media-gpu` | practical generation throughput | GPU-backed ComfyUI, model-heavy workflows |
| `builder` | page building and packaging | page-build workers, deploy helpers, asset consumers |
| `tools` | authoring and diagnostic extras | `n8n-mcp`, MCP servers, debugging surfaces |

Important rule:

- roles describe capability groups
- roles are not separate repos
- roles should compose cleanly

### 3. Node manifests

Each physical node should have a small manifest under `nodes/<node-name>/`
describing which roles it enables and any node-specific notes.

Examples:

- `nodes/vps`
- `nodes/engineering-pc`
- `nodes/local-builder`

The manifest is intentionally small. It should answer:

- which roles are enabled here
- which current target compose stack it resolves through
- what this node is optimized for
- which services are expected to be local vs remote
- what this node must not quietly try to do

In the current repo, node manifests use:

- `NODE_NAME`
- `TARGET`
- `ENABLED_ROLES`

## Recommended node split

### VPS

Recommended roles:

- `core`
- `vps`
- optional `media-cpu`
- optional `tools`

Purpose:

- stable shared substrate
- user-facing chat and automation
- continuity and artifact backbone
- page-building orchestration

The VPS is the canonical hub, but not the only execution surface.

### Engineering PC

Recommended roles:

- `core`
- `media-gpu`
- optional `tools`

Purpose:

- heavy ComfyUI generation
- workflow experimentation
- model-heavy media work

This node should not become an ad hoc second hub.

### Local builder / secondary node

Recommended roles:

- `core`
- `builder`
- optional `tools`

Purpose:

- site/page build workloads
- non-GPU experimentation
- isolated worker behavior

## GitHub model

Use a monorepo and keep `main` as the canonical branch.

Do not use:

- one branch per node
- separate repos for VPS vs local nodes
- machine-specific manual edits scattered across the tree

Instead:

- shared code and contracts live once
- role overlays live in shared repo paths
- node-specific selection lives in `nodes/<name>/`

This gives us:

- one history
- one review surface
- one workflow catalog
- fewer drift problems

## How core updates propagate safely

The propagation rule should be:

1. update shared core code or docs in shared paths
2. merge to `main`
3. each node pulls `main`
4. each node only activates the roles it declares locally

That means a broker schema fix, MinIO convention cleanup, or workflow payload
contract improvement can propagate to all nodes without also forcing every
machine to boot GPU media tools or builder-specific helpers.

The practical guardrail is:

- shared core should define interfaces and common behavior
- role overlays should define optional capability groups
- node manifests should decide what is live on a given machine

The first executable version of this now exists in `start-1215`:

- `./bin/start-1215 nodes`
- `./bin/start-1215 show-node vps`
- `./bin/start-1215 compose-cmd vps config`

The goal is to make node selection a repo-owned control-plane feature instead of
an operator remembering ad hoc docker commands.

The next step beyond manifest resolution is now also in place: selected roles
can contribute compose fragments through `stack/topology/roles.json`. That keeps
the common stack intact while still allowing role-specific overrides such as
CPU-safe vs GPU-intended ComfyUI behavior.

## Workflow portability rule

A workflow should declare what it needs rather than silently assuming every node
has every capability.

Examples:

- `requirements: ["broker", "minio", "n8n"]`
- `requirements: ["comfyui", "gpu-preferred"]`
- `requirements: ["ffmpeg"]`

This keeps routing explicit and avoids hidden fallbacks that make debugging
harder.

## Current prototype mapping

`stack/prototype-local` is the first concrete proof of the model. Today it is
effectively acting like:

- `core`
- `vps`
- optional `media-cpu`
- optional `tools`

That is useful because it lets us validate:

- the shared continuity contracts
- the local artifact path
- Open WebUI -> `n8n` -> broker
- Open WebUI -> `n8n` -> ComfyUI -> MinIO

before splitting those capabilities across multiple machines.

## When to split

A capability should move out of the VPS prototype when one of these becomes
true:

- it has a distinct hardware requirement such as GPU media generation
- it has a distinct risk posture such as aggressive experimentation
- it has a materially different uptime requirement than the shared hub
- it causes the VPS to carry complexity that most nodes do not need

That is the signal to turn a proven role into a separately deployed node.

## Immediate repo convention

The repo is ready for the split model when these paths are treated as canonical:

- `docs/architecture/` for contracts and operating model
- `stack/roles/` for role overlay intent and future compose fragments
- `nodes/<node-name>/` for node manifests
- `stack/prototype-local/` for the first runnable proof of the substrate

Those paths now exist so the future split has a defined place to land.
