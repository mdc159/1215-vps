---
name: run-shell
description: Run a short shell command (non-interactive, with a hard timeout) inside HERMES_ZERO_WORKSPACE. Captures stdout, stderr, exit code. Use this for mechanical verification — running linters, tests, git status, docker compose config, etc. NOT for long-running processes.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes-zero, seed, shell, verification]
    related_skills: [git-commit]
---

# run-shell — mechanically verify something by shelling out

## When to use

Tier-0 work is almost entirely mechanical verification: "run the tests
and tell me they passed", "print `git status`", "show me `docker compose
config` for the node manifest". `run-shell` is the verification primitive
that makes those invocations auditable.

Do NOT use this for:
- Starting long-running processes (use systemd unit installers instead).
- Anything that needs a TTY / interactive input.
- Commands outside the workspace — the skill `cd`s into
  `HERMES_ZERO_WORKSPACE` before executing and will not let you escape
  via `cd /` inside the command string (the skill re-verifies cwd on
  return).

## Contract

- Command is passed as a single positional string and executed via
  `bash -c`. No shell metacharacter escaping is attempted; you are
  responsible for your own quoting.
- Hard timeout is 120 seconds by default. Override with `--timeout N`.
  Exceeding it kills the process group.
- stdout and stderr are captured and emitted on their respective
  streams; the final line on stderr is always `exit=N` so a tier-1
  supervisor can grep for it.
- `--allow-write` (default off) is a semantic hint: skills that alter
  files should declare it. The skill does not technically enforce
  read-only, but the flag must be present for tier-1 supervisors to
  accept the call as "intentionally mutating".

## Usage

```bash
scripts/run_shell.py "ls -la"
scripts/run_shell.py --timeout 300 "uv run pytest -q"
scripts/run_shell.py --allow-write "git add -A && git status --short"
```

## Exit codes

Mirror the command's exit code. `-1` is reserved for timeouts (actual
value 124, matching `coreutils timeout`).
