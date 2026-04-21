# hermes-zero seed (tier-0 bootstrap agent)

**Status:** prototype. Available under `./bin/1215 seed-hermes` on the
`proto` branch. See
[`opus-recomendations.md`](./opus-recomendations.md) for the design
rationale (*Two-tier bootstrap*).

## What this is

`hermes-zero` is a deliberately minimal Hermes profile used to drive
**tier-1 mechanical work** — image digest pinning, template
re-rendering, commit cadence, file moves, `docker compose config`
verification, etc. It is structurally isolated from the Phase C
`orchestrator-ceo` profile:

| Dimension | `orchestrator-ceo` | `hermes-zero` |
|---|---|---|
| Profile root | `/var/lib/hermes/orchestrator-ceo/` | `/var/lib/hermes/hermes-zero/` |
| Workspace | `/var/lib/paperclip/workspaces/orchestrator-ceo/` | `/var/lib/paperclip/workspaces/hermes-zero/` |
| Memory | Honcho (shared Postgres) | none |
| Canary | `HERMES_CEO_CANARY` | `HERMES_ZERO_CANARY` |
| Skills | `continuity-plane/` (broker + MinIO + Langfuse) | `hermes-zero/` (stdlib only) |
| Broker dependency | required | optional |
| Can run without substrate? | no | **yes** |

That last row is the whole point: `hermes-zero` is the agent you can
bring up *before* Phase 0 / A is finished, so it can help finish
Phase 0 / A.

## Seed skills

Five skills, all stdlib-only, all workspace-scoped, all canary-checked:

| Skill | Purpose |
|---|---|
| `read-file` | Print a workspace file to stdout (UTF-8, truncation-aware). |
| `write-file` | Atomically overwrite a workspace file from stdin. |
| `append-file` | Append to a workspace file (mkdir-p parents, JSONL-friendly). |
| `run-shell` | Run a short `bash -c` command with hard timeout, inside the workspace. |
| `git-commit` | Stage + commit with a `[hermes-zero] ` prefix; canary-checks the staged diff. |

Source:
[`stack/services/hermes-gateway/skills/hermes-zero/`](../../stack/services/hermes-gateway/skills/hermes-zero/).
Every skill documents its exit-code contract in its `SKILL.md`; tier-1
supervisors can grep for `ERROR:` to flag failures without parsing
structured output.

## Install

```bash
# Renders /var/lib/hermes/hermes-zero/ and installs all 5 skills.
# Reads OPENROUTER_API_KEY from stack/prototype-local/.env if present,
# or from HERMES_ZERO_OPENROUTER_API_KEY as a day-zero fallback.
./bin/1215 seed-hermes

# Regenerate config.yaml / .env / skill tree (preserves canary):
./bin/1215 seed-hermes --force

# Opt into Langfuse tracing for tier-0 runs (off by default):
./bin/1215 seed-hermes --enable-langfuse
```

The underlying script is `stack/services/hermes-gateway/scripts/seed_hermes_zero.sh`;
the `bin/1215` subcommand is a thin wrapper for operator ergonomics.

## Smoke it

```bash
# Hermes sees the seed skills.
HERMES_HOME=/var/lib/hermes/hermes-zero/.hermes \
  modules/hermes-agent/.venv/bin/hermes skills list

# Exercise the skills directly (no LLM yet).
export HERMES_ZERO_WORKSPACE=/var/lib/paperclip/workspaces/hermes-zero
export HERMES_ZERO_CANARY="FAKE_ZERO_SECRET_DO_NOT_LEAK_1215_Q9P3M7XN"
echo "hello" | \
  /var/lib/hermes/hermes-zero/.hermes/skills/hermes-zero/write-file/scripts/write_file.py test.md
/var/lib/hermes/hermes-zero/.hermes/skills/hermes-zero/read-file/scripts/read_file.py test.md
```

## Tier-1 pilot — first task

The point of the seed is to let a tier-0 agent help finish tier-0's own
substrate. A good first task:

> Open `stack/prototype-local/docker-compose.substrate.yml`. For every
> image that is pinned to a tag but not a `@sha256:...` digest, use
> `docker buildx imagetools inspect` to resolve the digest, then rewrite
> the compose file so every image line is `image@sha256:<digest>`.
> Commit each image in its own commit with message
> `pin <service> image digest`.

That's exactly the kind of mechanical, verifier-friendly work that
exposed most of the Phase A pitfalls — and it's work the tier-0 agent
can do safely because:

- the workspace would be a *clone* of the repo at
  `/var/lib/paperclip/workspaces/hermes-zero/1215-vps/`, not the
  checkout you're editing in your IDE,
- every write goes through `write-file` / `append-file` with a canary
  guard,
- every verification goes through `run-shell` with a 120-second
  timeout,
- every commit goes through `git-commit` with `[hermes-zero] ` in the
  message — trivially `git log --grep`-able,
- you cherry-pick the tier-0 commits into `proto` yourself once you've
  eyeballed the diff. Tier-0 never pushes.

## What tier-0 is **not** for

- **Architectural judgment.** "Should we merge Phase C and F?" is a
  decision that has to happen in your head (or a brainstorming chat),
  not a skill call.
- **Long-horizon tasks.** `memory.provider: none` is intentional. If a
  task needs to remember anything across runs, promote it to
  `orchestrator-ceo`.
- **Anything that talks to the substrate.** The seed skills have no
  broker client, no MinIO client, no Honcho client. Tier-0 is a file /
  shell / git agent. Nothing more.
- **Self-review.** Tier-0 must not be the one who verifies its own
  commits. The human (or a separate tier-1/2 reviewer) runs the
  canary sweep, reads the diff, and decides whether to cherry-pick.

## Relationship to the execution plan

| Phase | tier-0's role | tier-1's (human's) role |
|---|---|---|
| 0 — substrate + broker schema + canary protocol | render compose deltas, pin digests, commit | design schema, own canary protocol, review |
| A — image pinning + manifests + CI gate | pin remaining digests, generate manifests from template | author CI gate, verify reproducibility |
| B — Honcho on shared Postgres | write systemd unit templates | validate Postgres permissions, memory semantics |
| C — hermes-gateway daemon | scaffold FastAPI handlers, test stubs | threat-model the spawn path, allowlist design |
| D — orchestrator-ceo profile + skills | install skill tree, `--force` regenerate on template drift | design skill contracts, Langfuse trace design |
| E — Paperclip container | bridge-network compose edits, DNS-based client updates | validate host ↔ container boundary |
| F — Langfuse instrumentation | propagate env vars across templates | design trace_id / session_id correlation |
| G — Unified launch script | author `do_*` functions, add status-table columns | design the lifecycle state machine |
| H (new) — CI gate | author GitHub Actions YAML, smoke-job matrix | decide which invariants are blocking |

## Rotating the canary

```bash
# Generates a new HERMES_ZERO_CANARY while keeping everything else.
sed -i '/^HERMES_ZERO_CANARY=/d' /var/lib/hermes/hermes-zero/.hermes/.env
./bin/1215 seed-hermes --force
```

After rotation, re-grep every file tier-0 produced for the *old*
canary value. A hit means the old canary escaped before rotation and
you should treat that output as compromised.
