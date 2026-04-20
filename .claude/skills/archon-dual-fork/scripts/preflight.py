#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Preflight check for archon-dual-fork.

Verifies Codex CLI is installed and detects the available sandbox tier.
Emits a JSON report. Non-zero exit if Codex is missing (hard requirement).

Sandbox tiers:
  bwrap   — bubblewrap present (native Linux isolation, no API key, free)
  e2b     — E2B_API_KEY env var set (remote sandbox, costs money)
  none    — neither available; sandbox seat skipped
"""
from __future__ import annotations

import json
import os
import shutil
import sys


def check(tool: str) -> bool:
    return shutil.which(tool) is not None


def detect_sandbox() -> dict:
    has_bwrap = check("bwrap")
    has_e2b_key = bool(os.environ.get("E2B_API_KEY"))
    # bwrap is preferred when available — no API key, no cost
    if has_bwrap:
        tier = "bwrap"
    elif has_e2b_key:
        tier = "e2b"
    else:
        tier = "none"
    return {
        "tier": tier,
        "bwrap_available": has_bwrap,
        "e2b_key_present": has_e2b_key,
    }


def main() -> int:
    codex_ok = check("codex")
    sandbox = detect_sandbox()

    report = {
        "codex_installed": codex_ok,
        "sandbox": sandbox,
        "platform": sys.platform,
        "ready": codex_ok,  # Codex is the only hard requirement
    }

    print(json.dumps(report, indent=2))

    if not codex_ok:
        print("\nERROR: Codex CLI not found. Install: npm install -g @openai/codex",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
