---
name: git-commit
description: Stage and commit changes in the workspace's git repo with a caller-provided message. Refuses to commit if the staged diff leaks the canary. Use this to close a tier-1 phase step with a single auditable action.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes-zero, seed, git, commit]
    related_skills: [run-shell]
---

# git-commit — stage + commit a tier-0 change

## When to use

At the end of a tier-0 phase step, once `run-shell` verification has
passed, call `git-commit` to turn the work into a single reviewable
unit. One commit per phase step is the target cadence.

## Contract

- The workspace must be a git repository (`.git/` must exist). Fails
  otherwise.
- `--paths` is a list of repo-relative paths to stage (default: `.`,
  i.e. everything). The skill validates every path resolves *inside*
  `HERMES_ZERO_WORKSPACE` before staging.
- `--message` is required. The skill prepends `[hermes-zero] ` to make
  tier-0-produced commits trivially `git log --grep`-able. The message
  body is subject to the same canary-leak check as `write-file`.
- If there is nothing to commit after staging, the skill exits `0` with
  a `no changes; nothing to commit` stderr note rather than failing —
  idempotent re-runs shouldn't crash tier-1 pipelines.
- Does NOT push. Pushing is a tier-2 decision.

## Usage

```bash
scripts/git_commit.py --message "pin langfuse-web image digest"
scripts/git_commit.py --paths docs/architecture/roadmap.md \
                      --message "add phase 0 retrospective"
```

## Exit codes

- `0` — commit created (or nothing to commit).
- `2` — workspace guard failure.
- `5` — canary leak in message or staged diff.
- `8` — git operation failed (not a repo / staging error / etc.).
