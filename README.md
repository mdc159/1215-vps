# 1215-vps

`1215-vps` is being rebuilt as a prototype-first, architecture-driven system.
It is an autonomous, multi-surface business stack grown from a single local
prototype into a hardened VPS hub and, eventually, a multi-node topology.

The system centers on:

- a shared **continuity plane** (broker + Postgres) as system of record
- **`n8n`** as the trusted workflow nervous system
- **Open WebUI** as the primary human-facing shell
- **Paperclip** as the specialist orchestration surface
- **Hermes** as a host-native execution runtime behind a gateway boundary
- **ComfyUI** as the first specialist worker (media generation via `n8n`)

Implementation strategy:

1. Build the **local prototype** as the first concrete node implementation.
2. Use that prototype to validate the continuity contracts and node pattern.
3. Promote the validated architecture into the hardened **VPS hub**.

## Architecture Review Pack

The full design lives in `docs/architecture/`. Read these in order:

1. [`north-star.md`](docs/architecture/north-star.md) — target architecture.
2. [`current-state.md`](docs/architecture/current-state.md) — factual snapshot
   of what is in this repository today.
3. [`roadmap.md`](docs/architecture/roadmap.md) — ordered phases that close
   the gap between current state and north star.
4. [`execution-plan.md`](docs/architecture/execution-plan.md) — the concrete,
   commit-by-commit execution plan for a working session.
5. [`node-roles.md`](docs/architecture/node-roles.md) — node responsibilities
   and promotion policy across VPS, prototype, engineering, and research nodes.
6. [`overview.md`](docs/architecture/overview.md) — legacy reference only
   (carries a deprecation banner; superseded by the four documents above).

## Current Status

- Branch: **`proto`**. `main` is the stable reference.
- Phase 0 (branch hygiene + trim + plan alignment) is complete.
- The prototype is **not** fully assembled yet: Honcho, the Hermes gateway,
  the `orchestrator-ceo` profile, the Paperclip container, and the unified
  launch script all land in later phases (A → H) defined in `roadmap.md` and
  executed per `execution-plan.md`.
- Local bringup instructions live in
  [`stack/prototype-local/README.md`](stack/prototype-local/README.md).

If you are a fresh agent session, start at
[`docs/architecture/execution-plan.md`](docs/architecture/execution-plan.md)
and follow the **Session Kickoff** block verbatim.

## Repo Layout

| Path | Contents |
|---|---|
| `docs/architecture/` | Review pack: north-star, current-state, roadmap, execution-plan, node-roles (+ legacy overview). |
| `stack/prototype-local/` | Local-node Docker Compose stack and bringup scripts (the only runnable target today). |
| `stack/broker/` | Broker FastAPI service source (the continuity plane API). |
| `stack/sql/` | Broker schema migrations. |
| `stack/topology/` | Repo-owned target, service, and role manifests. |
| `stack/roles/` | Per-role Docker Compose overlays (scaffolded; partially populated). |
| `stack/control/` | Control-plane CLI (`start-1215`). Phase H rebuilds this as `bin/1215`. |
| `stack/services/` | (Reserved for Phase B–D: Honcho + Hermes gateway host-native units.) |
| `modules/` | Upstream source submodules referenced by the prototype. |
| `claude-memory-compiler/` | Reference submodule (memory compiler; not wired into runtime). |

## Control CLI (current)

Until Phase H lands `bin/1215`, the control CLI is invoked directly via
`uv`:

```bash
cd stack/control
uv sync
uv run start-1215 doctor
uv run start-1215 targets
uv run start-1215 services --target prototype-local
uv run start-1215 docs
```

These commands validate prerequisites and expose the topology manifests;
they do **not** bring up services yet. Bringup lives in
`stack/prototype-local/scripts/setup_hermes_honcho_paperclip.py` and
`docker-compose.substrate.yml` today, and will be subsumed by
`./bin/1215 up` in Phase H.

## Upstream Module References

Declared in [`.gitmodules`](.gitmodules):

- `modules/local-ai-packaged`
- `modules/hermes-agent`
- `modules/hermes-paperclip-adapter`
- `modules/hermes-agent-self-evolution`
- `modules/autoreason`
- `modules/paperclip`
- `modules/honcho`
- `modules/n8n-mcp`

These are reference-only — the prototype does not fork or vendor them.
