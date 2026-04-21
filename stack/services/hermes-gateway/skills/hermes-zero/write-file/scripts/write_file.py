#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Atomically write a workspace file from stdin (hermes-zero seed skill)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _workspace import die, resolve_in_workspace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="File path relative to HERMES_ZERO_WORKSPACE.")
    parser.add_argument(
        "--mode",
        default="0644",
        help="Octal mode for the final file (default 0644).",
    )
    parser.add_argument(
        "--canary-check",
        choices=("on", "off"),
        default="on",
        help="Refuse the write if the payload contains HERMES_ZERO_CANARY. Default on.",
    )
    args = parser.parse_args()

    try:
        target = resolve_in_workspace(args.path)
    except Exception as exc:
        die(str(exc), code=2)

    try:
        mode = int(args.mode, 8)
    except ValueError:
        die(f"invalid --mode {args.mode!r}; expected octal like 0644", code=2)

    payload = sys.stdin.read()

    if args.canary_check == "on":
        canary = os.environ.get("HERMES_ZERO_CANARY", "").strip()
        if canary and canary in payload:
            die(
                f"refusing write: payload contains HERMES_ZERO_CANARY. "
                f"Re-run with --canary-check=off if this is intentional.",
                code=5,
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except OSError as exc:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        die(f"write failed: {exc}", code=6)

    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
