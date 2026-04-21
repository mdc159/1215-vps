---
name: append-file
description: Append text to a file under HERMES_ZERO_WORKSPACE, creating it and any parent directories if needed. Use this for incremental logs, dev journals, and phase records where history matters.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes-zero, seed, filesystem, append]
    related_skills: [write-file, read-file]
---

# append-file — add a line/block to a workspace file

## When to use

Use for anything where **history matters**:
- Dev journals, phase logs, decision logs.
- Accumulating outputs across multiple skill calls.
- Growing a structured record (JSONL) one line at a time.

Do NOT use for replacing file content — use `write-file`.

## Contract

- `path` is relative to `HERMES_ZERO_WORKSPACE`. Rejected otherwise.
- Payload comes from stdin as UTF-8 text.
- Parent dirs are `mkdir -p`'d; the file is created if missing.
- `--ensure-trailing-newline` (default on) adds `\n` to the payload if
  it doesn't already end with one. Disable for JSONL where the
  producer is expected to emit its own newline.
- Canary-leak check identical to `write-file`.

## Usage

```bash
echo "phase 0 start: $(date -Iseconds)" | scripts/append_file.py logs/dev.log
printf '{"event":"phase.started","phase":"A"}\n' | \
  scripts/append_file.py --ensure-trailing-newline=off logs/events.jsonl
```

## Exit codes

Same as `write-file` (2/5/6). `0` on success.
