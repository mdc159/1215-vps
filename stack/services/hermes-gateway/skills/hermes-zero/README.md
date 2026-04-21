# hermes-zero seed skills

Five stdlib-only skills that make a tier-0 Hermes (`hermes-zero`) useful
without any substrate dependencies. See
[`docs/architecture/opus-recomendations.md`](../../../../docs/architecture/opus-recomendations.md)
(*Two-tier bootstrap*) for why they exist.

| Skill | Purpose | Mutating? |
|-------|---------|-----------|
| `read-file` | Print a workspace file to stdout. | no |
| `write-file` | Atomically overwrite a workspace file from stdin. | yes |
| `append-file` | Append stdin to a workspace file. | yes |
| `run-shell` | Run a short shell command inside the workspace. | advisory |
| `git-commit` | Stage + commit staged changes with a canary check. | yes |

## Contracts common to all five

- **Workspace-scoped.** Every path resolves under
  `HERMES_ZERO_WORKSPACE` (set by the seed installer to
  `/var/lib/paperclip/workspaces/hermes-zero`). Absolute paths and `..`
  escapes are rejected with exit code `2`.
- **Canary-aware.** Mutating skills (`write-file`, `append-file`,
  `git-commit`) refuse to persist content that contains
  `HERMES_ZERO_CANARY`. Tier-1 supervisors can rotate the canary to
  detect accidental secret propagation.
- **Exit-code-driven.** Every skill exits with a meaningful code and
  prefixes fatal errors with `ERROR:` on stderr so grep-based tier-1
  supervisors can detect failures without parsing structured output.
- **Stdlib-only.** No PEP-723 dependencies declared. The seed must run
  on any Python ≥ 3.11 without network access.

## Relationship to the `continuity-plane` skills

`continuity-plane/` (Phase F) is for `orchestrator-ceo` — it assumes the
full substrate (broker, MinIO, Honcho, Langfuse) is running. The
`hermes-zero/` skills are a strict subset: they never talk to the
broker, never produce Langfuse spans, never write to Honcho. They exist
precisely so a tier-0 agent can come up before any of that
infrastructure is available.

If you find yourself wanting broker emission from a tier-0 skill,
that's a signal to either (a) promote the task to `orchestrator-ceo`
or (b) add a *separate* `hermes-zero-broker/` skill pack gated behind
a `--broker` flag, rather than making the core five depend on network
reachability.
