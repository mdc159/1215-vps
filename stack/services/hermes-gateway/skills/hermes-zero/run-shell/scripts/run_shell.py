#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run a short shell command inside HERMES_ZERO_WORKSPACE (hermes-zero seed skill).

Executes via ``bash -c`` with the workspace as cwd. Stdout/stderr are
forwarded; a trailing ``exit=N`` line is appended to stderr so tier-1
supervisors can grep the final status without parsing return codes.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _workspace import die, workspace_root  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="Shell command (single argument).")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Hard timeout in seconds (default 120).",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Advisory flag that this command may mutate state.",
    )
    args = parser.parse_args()

    try:
        cwd = workspace_root()
    except Exception as exc:
        die(str(exc), code=2)

    env = os.environ.copy()
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")

    try:
        proc = subprocess.Popen(
            ["bash", "-c", args.command],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        die(f"failed to spawn bash: {exc}", code=7)

    try:
        stdout, stderr = proc.communicate(timeout=args.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = proc.communicate()
        sys.stdout.write(stdout or "")
        sys.stderr.write(stderr or "")
        sys.stderr.write(f"ERROR: timeout after {args.timeout}s\nexit=124\n")
        return 124

    sys.stdout.write(stdout or "")
    sys.stderr.write(stderr or "")
    if stderr and not stderr.endswith("\n"):
        sys.stderr.write("\n")
    sys.stderr.write(f"exit={rc}\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
