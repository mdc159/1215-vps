"""Shared workspace guard for hermes-zero seed skills.

All tier-0 skills are pinned to ``HERMES_ZERO_WORKSPACE`` (set by the
seed installer in ``.env`` to
``/var/lib/paperclip/workspaces/hermes-zero`` by default). Skills refuse
to read or write anywhere else — this is the single structural defense
against a tier-0 agent wandering into the orchestrator-ceo profile or
the substrate data dirs.

Stdlib-only on purpose: the seed must not depend on any wheel that
isn't already present on a minimal Python install.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class WorkspaceError(RuntimeError):
    """Raised when a skill would touch a path outside the workspace."""


def workspace_root() -> Path:
    raw = os.environ.get("HERMES_ZERO_WORKSPACE")
    if not raw:
        raise WorkspaceError(
            "HERMES_ZERO_WORKSPACE is not set. Re-run "
            "stack/services/hermes-gateway/scripts/seed_hermes_zero.sh to "
            "regenerate the profile .env."
        )
    root = Path(raw).resolve()
    if not root.exists():
        raise WorkspaceError(f"workspace root does not exist: {root}")
    if not root.is_dir():
        raise WorkspaceError(f"workspace root is not a directory: {root}")
    return root


def resolve_in_workspace(relpath: str) -> Path:
    """Resolve ``relpath`` relative to the workspace root.

    Rejects absolute paths, ``..`` escapes, and anything that resolves
    outside the workspace even via symlinks.
    """
    if not relpath:
        raise WorkspaceError("path is empty")
    candidate = Path(relpath)
    if candidate.is_absolute():
        raise WorkspaceError(
            f"absolute paths are not allowed (got {relpath!r}); use paths "
            "relative to HERMES_ZERO_WORKSPACE"
        )
    root = workspace_root()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError(
            f"path {relpath!r} resolves outside the workspace: {resolved}"
        ) from exc
    return resolved


def die(message: str, code: int = 2) -> None:
    """Write ``message`` to stderr and exit with a non-zero status.

    Tier-1 supervisors grep for ``ERROR:`` to flag failed skill calls.
    """
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)
