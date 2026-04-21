---
name: write-file
description: Write a full file under HERMES_ZERO_WORKSPACE. Creates parent directories as needed. Overwrites atomically via tmp+rename. Use this for producing new files or fully regenerating existing ones from a template.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes-zero, seed, filesystem, write]
    related_skills: [read-file, append-file]
---

# write-file — atomically write a workspace file

## When to use

Use for:
- Creating a brand-new file.
- Fully replacing an existing file from a new template (e.g. regenerating
  `.env` after a variable change).

Do NOT use for appending to an existing file — use `append-file` instead.
Atomic overwrite is destructive by design.

## Contract

- `path` is relative to `HERMES_ZERO_WORKSPACE`. Rejected otherwise.
- Content is read from stdin as UTF-8 text. Binary writes are not
  supported in the seed (add a later skill if you actually need one).
- Writes are atomic: content goes to `path.tmp.<pid>` then `os.replace`
  into place, so a crash mid-write never leaves a half-written file.
- `--canary-check` (default on) refuses the write if the payload
  contains `HERMES_ZERO_CANARY`'s value. Opt out with
  `--canary-check=off` only if you are deliberately testing the
  canary-leak alarm.

## Usage

```bash
echo "# new notes" | scripts/write_file.py path/to/notes.md
cat template.in | scripts/write_file.py --mode 0600 secrets/session.env
```

## Exit codes

- `0` — success (prints the final absolute path to stdout).
- `2` — workspace guard failure.
- `5` — canary leak detected.
- `6` — I/O error during write.
