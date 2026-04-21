#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read a workspace file and print it to stdout (hermes-zero seed skill)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _workspace import die, resolve_in_workspace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="File path relative to HERMES_ZERO_WORKSPACE.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=1_048_576,
        help="Truncate reads above this size (default 1 MiB).",
    )
    args = parser.parse_args()

    try:
        target = resolve_in_workspace(args.path)
    except Exception as exc:
        die(str(exc), code=2)

    if not target.exists():
        die(f"file not found: {args.path}", code=3)
    if not target.is_file():
        die(f"not a regular file: {args.path}", code=3)

    try:
        data = target.read_bytes()
    except OSError as exc:
        die(f"read failed: {exc}", code=3)

    truncated = False
    if len(data) > args.max_bytes:
        data = data[: args.max_bytes]
        truncated = True

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        die(f"file is not UTF-8: {exc}", code=4)

    sys.stdout.write(text)
    if truncated:
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write(f"... [truncated after {args.max_bytes} bytes]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
