#!/usr/bin/env python3
"""Repo-root shim for the 1215-VPS control CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PROJECT = REPO_ROOT / "stack" / "control"

if not (CONTROL_PROJECT / "pyproject.toml").exists():
    sys.exit(
        "error: expected stack/control/pyproject.toml under the current checkout"
    )

os.chdir(REPO_ROOT)
os.execvp(
    "uv",
    [
        "uv",
        "run",
        "--project",
        str(CONTROL_PROJECT),
        "start-1215",
        *sys.argv[1:],
    ],
)
