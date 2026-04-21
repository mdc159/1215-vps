#!/usr/bin/env python3
"""Run the prototype-local shared-core gate checks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import REPO_ROOT, require_command


def run_step(script: Path, *, timeout: int) -> None:
    if not script.exists():
        raise SystemExit(f"missing required gate script: {script}")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(f"gate step failed: {script.name}")
    if result.stdout:
        print(result.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=300, help="Per-step timeout in seconds.")
    args = parser.parse_args()

    require_command("docker")

    scripts = [
        REPO_ROOT / "stack" / "prototype-local" / "scripts" / "bootstrap_n8n.py",
        REPO_ROOT / "stack" / "prototype-local" / "scripts" / "sync_openwebui_functions.py",
        REPO_ROOT / "stack" / "prototype-local" / "scripts" / "test_openwebui_n8n_broker.py",
        REPO_ROOT / "stack" / "prototype-local" / "scripts" / "test_n8n_mcp_functional.py",
    ]
    for script in scripts:
        run_step(script, timeout=args.timeout)

    print("prototype-local shared-core gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
