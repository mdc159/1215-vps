"""Thin wrappers around `docker compose` invocations."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping


class ComposeError(RuntimeError):
    """Raised when `docker compose` exits non-zero."""


def build_command(
    project: str,
    compose_files: list[Path],
    subcommand: list[str],
) -> list[str]:
    """Construct a `docker compose` argv list."""
    if not compose_files:
        raise ValueError("at least one compose file required")

    cmd = ["docker", "compose", "-p", project]
    for compose_file in compose_files:
        cmd.extend(["-f", str(compose_file)])
    cmd.extend(subcommand)
    return cmd


def run(
    project: str,
    compose_files: list[Path],
    subcommand: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose`, optionally raising on non-zero exit."""
    cmd = build_command(project, compose_files, subcommand)
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=dict(os.environ if env is None else env),
    )
    if check and result.returncode != 0:
        stderr = result.stderr if capture else "(see terminal output)"
        raise ComposeError(
            f"docker compose {' '.join(subcommand)} failed with exit "
            f"{result.returncode}: {stderr}"
        )
    return result
