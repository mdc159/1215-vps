#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stage + commit workspace changes (hermes-zero seed skill).

Auto-prepends ``[hermes-zero] `` to the commit message so tier-0
commits are greppable in history. Canary-checks the commit message
AND the staged diff before finalizing.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _workspace import die, resolve_in_workspace, workspace_root  # noqa: E402


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        die(
            f"git {' '.join(args)} failed (rc={result.returncode}): "
            f"{result.stderr.strip()}",
            code=8,
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--message",
        required=True,
        help="Commit message (will be prefixed with '[hermes-zero] ').",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Paths to stage (relative to workspace). Default: everything.",
    )
    args = parser.parse_args()

    try:
        cwd = workspace_root()
    except Exception as exc:
        die(str(exc), code=2)

    if not (cwd / ".git").exists():
        die(f"not a git repo: {cwd}", code=8)

    canary = os.environ.get("HERMES_ZERO_CANARY", "").strip()

    if canary and canary in args.message:
        die("refusing commit: message contains HERMES_ZERO_CANARY", code=5)

    if args.paths:
        for rel in args.paths:
            try:
                resolve_in_workspace(rel)
            except Exception as exc:
                die(str(exc), code=2)
        run_git(["add", "--", *args.paths], cwd)
    else:
        run_git(["add", "-A"], cwd)

    diff = run_git(["diff", "--cached"], cwd, check=False)
    if canary and canary in diff.stdout:
        run_git(["reset"], cwd, check=False)
        die("refusing commit: staged diff contains HERMES_ZERO_CANARY", code=5)

    status = run_git(["status", "--porcelain"], cwd)
    if not any(line and line[0] != " " and line[0] != "?" for line in status.stdout.splitlines()):
        sys.stderr.write("no changes; nothing to commit\n")
        return 0

    message = f"[hermes-zero] {args.message}"
    commit = run_git(["commit", "-m", message], cwd, check=False)
    if commit.returncode != 0:
        die(f"commit failed: {commit.stderr.strip() or commit.stdout.strip()}", code=8)

    sha = run_git(["rev-parse", "HEAD"], cwd).stdout.strip()
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
