#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Append stdin to a workspace file (hermes-zero seed skill)."""

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
        "--ensure-trailing-newline",
        choices=("on", "off"),
        default="on",
        help="Ensure payload ends with \\n (default on; turn off for JSONL).",
    )
    parser.add_argument(
        "--canary-check",
        choices=("on", "off"),
        default="on",
        help="Refuse if payload contains HERMES_ZERO_CANARY. Default on.",
    )
    args = parser.parse_args()

    try:
        target = resolve_in_workspace(args.path)
    except Exception as exc:
        die(str(exc), code=2)

    payload = sys.stdin.read()

    if args.canary_check == "on":
        canary = os.environ.get("HERMES_ZERO_CANARY", "").strip()
        if canary and canary in payload:
            die(
                "refusing append: payload contains HERMES_ZERO_CANARY",
                code=5,
            )

    if args.ensure_trailing_newline == "on" and payload and not payload.endswith("\n"):
        payload += "\n"

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(payload)
    except OSError as exc:
        die(f"append failed: {exc}", code=6)

    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
