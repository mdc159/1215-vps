---
name: read-file
description: Read a UTF-8 text file under HERMES_ZERO_WORKSPACE and print it to stdout. Fails if the path escapes the workspace. Use this whenever you need to inspect a file before editing it.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes-zero, seed, filesystem, read]
    related_skills: [write-file, append-file]
---

# read-file — print a workspace file to stdout

## When to use

Tier-0 file inspection. Use this before any `write-file` call so you know
what you're about to overwrite, and before any `git-commit` so you can
confirm what will land.

## Contract

- `path` is relative to `HERMES_ZERO_WORKSPACE`. Absolute paths and
  `..` escapes are rejected with a non-zero exit.
- File must exist and be UTF-8 decodable. Missing files or binary
  blobs produce a non-zero exit with a grep-able `ERROR:` prefix.
- Output is the raw file content on stdout. No framing, no JSON.
- `--max-bytes N` (default 1 MiB) truncates large reads with a trailing
  `... [truncated after N bytes]` marker so a tier-1 supervisor can tell
  truncation from "file naturally ends here".

## Usage

```bash
scripts/read_file.py path/to/notes.md
scripts/read_file.py --max-bytes 65536 logs/large.log
```

## Exit codes

- `0` — success.
- `2` — workspace guard failure (path escape, missing env, etc.).
- `3` — file does not exist.
- `4` — file is not UTF-8.
