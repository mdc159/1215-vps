"""Allowlists + argv/env/cwd construction for `hermes chat` subprocesses.

The gateway's security model lives here. Everything in this module is
synchronous and has no FastAPI / httpx dependency so the allowlist and
argv construction logic can be unit-tested without spinning up the app.

Rules the spawn layer enforces (all of these must hold before we
return a `SpawnPlan`, never after):

  1. `profile` MUST be in :data:`PROFILE_ALLOWLIST`.
  2. The resolved profile directory MUST exist on disk at
     ``<profile_root>/<profile>/.hermes`` and be the real path (no
     symlink escapes out of ``profile_root``).
  3. The resolved workspace directory MUST exist on disk at
     ``<workspace_root>/<profile>`` and be the real path.
  4. ``PATH`` is a fixed, narrow string; the caller's PATH is ignored.
  5. Per-profile secrets come from ``<profile>/.hermes/.env`` ONLY.
     The request body never contributes env. Keys that would clobber
     PATH / HOME / HERMES_HOME are dropped silently.
  6. argv is always a list (never shell=True). ``hermes chat -Q -q
     <prompt>`` with ``--pass-session-id`` so the Hermes session gets
     the gateway-assigned id.

`build_spawn_plan` is deliberately pure and returns a dataclass —
`execute_spawn` is the thin wrapper around :class:`subprocess.Popen`
that actually forks.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_PROFILE_ROOT = Path("/var/lib/hermes")
DEFAULT_WORKSPACE_ROOT = Path("/var/lib/paperclip/workspaces")
DEFAULT_HERMES_BIN = Path(
    "/home/hammer/Documents/repos/1215-vps/modules/hermes-agent/.venv/bin/hermes"
)

# Narrow, hermetic PATH. Do NOT inherit the gateway's PATH: if the
# daemon is launched from a shell with /home/hammer/.local/bin at the
# front, a compromised profile .env could still not redirect `hermes`
# via PATH since we resolve the binary by absolute path, but locking
# PATH down also prevents Hermes-internal shellouts from finding
# user-installed impostors.
FIXED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

PROFILE_ALLOWLIST: frozenset[str] = frozenset({"orchestrator-ceo"})

# Env keys we will never forward from a profile .env into the child —
# these are either set by `build_spawn_plan` itself (HERMES_HOME, PATH,
# HOME) or are security-sensitive in ways a profile .env shouldn't
# control (LD_PRELOAD, LD_LIBRARY_PATH, PYTHONPATH).
_BLOCKED_ENV_KEYS: frozenset[str] = frozenset(
    {
        "HERMES_HOME",
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONHOME",
    }
)


class SpawnRejected(Exception):
    """Raised when an incoming StartRun fails policy checks.

    The FastAPI layer translates this to HTTP 403 (policy) or 400
    (malformed). The ``reason`` attribute is a short machine-readable
    tag for logs and broker metadata.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class SpawnPlan:
    """Fully resolved, policy-approved spawn parameters.

    ``argv[0]`` is always an absolute path to the Hermes binary. The
    app layer is expected to hand this directly to
    :func:`subprocess.Popen(argv, env=env, cwd=str(cwd), ...)`.
    """

    run_id: str
    session_id: str
    profile: str
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    hermes_home: Path
    workspace: Path

    def pretty(self) -> str:
        """Human-readable argv suitable for logs (no secret values)."""
        return " ".join(shlex.quote(a) for a in self.argv)


def _require_non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpawnRejected("bad_request", f"{field_name} must be a non-empty string")
    return value


def _resolve_under(root: Path, leaf: str, *, kind: str) -> Path:
    """Resolve ``root / leaf`` and confirm it stays under ``root``.

    Prevents ``profile="../foo"`` from escaping the allowlist via
    symlinks. We do NOT auto-create the leaf — the Phase C installer
    (or its equivalent for future profiles) is responsible for that.
    """
    # leaf came from a request; clamp to a single path component.
    if "/" in leaf or leaf in {"", ".", ".."}:
        raise SpawnRejected("bad_request", f"{kind} must be a single path component")
    try:
        resolved = (root / leaf).resolve(strict=True)
    except FileNotFoundError as exc:
        raise SpawnRejected(
            "not_found", f"{kind} directory does not exist: {root / leaf}"
        ) from exc
    root_resolved = root.resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SpawnRejected(
            "forbidden", f"{kind} path escapes {root_resolved}"
        ) from exc
    if not resolved.is_dir():
        raise SpawnRejected("bad_request", f"{kind} path is not a directory: {resolved}")
    return resolved


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file.

    - Lines starting with ``#`` or blank are ignored.
    - Values are taken verbatim (no shell unquoting) — the Hermes
      profile .env is generated by
      :file:`scripts/setup_ceo_profile.sh` and never hand-edited with
      shell-quoted values, so supporting quoting here would just be
      attack surface.
    - Blocked keys (PATH / HOME / HERMES_HOME / LD_* / PYTHON*) are
      silently dropped so a compromised .env cannot hijack the child.

    Raises :class:`FileNotFoundError` if ``path`` is missing; callers
    decide whether that's a policy failure or a bootstrap bug.
    """
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                raise SpawnRejected(
                    "bad_env_file",
                    f"{path}:{line_no} is not KEY=VALUE",
                )
            key, _, value = stripped.partition("=")
            key = key.strip()
            if not key or not key.replace("_", "").isalnum():
                raise SpawnRejected(
                    "bad_env_file", f"{path}:{line_no} has invalid key {key!r}"
                )
            if key in _BLOCKED_ENV_KEYS:
                continue
            out[key] = value
    return out


def build_spawn_plan(
    *,
    run_id: str,
    session_id: str,
    profile: str,
    prompt: str,
    profile_root: Path = DEFAULT_PROFILE_ROOT,
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
    hermes_bin: Path = DEFAULT_HERMES_BIN,
    model: str | None = None,
    extra_argv: Iterable[str] = (),
) -> SpawnPlan:
    """Construct a SpawnPlan after enforcing every policy check.

    This function NEVER performs IO other than stat-style existence
    checks and reading the profile .env. It must not write, network,
    or mutate state — so a test can call it tens of thousands of times
    without side effects.
    """

    run_id = _require_non_empty(run_id, "run_id")
    session_id = _require_non_empty(session_id, "session_id")
    profile = _require_non_empty(profile, "profile")
    prompt = _require_non_empty(prompt, "prompt")

    if profile not in PROFILE_ALLOWLIST:
        raise SpawnRejected(
            "forbidden",
            f"profile {profile!r} is not in the allowlist "
            f"(allowed: {sorted(PROFILE_ALLOWLIST)})",
        )

    if not hermes_bin.is_absolute():
        raise SpawnRejected("config", f"hermes_bin must be absolute: {hermes_bin}")
    if not hermes_bin.exists():
        raise SpawnRejected("config", f"hermes binary not found: {hermes_bin}")
    if not os.access(hermes_bin, os.X_OK):
        raise SpawnRejected("config", f"hermes binary is not executable: {hermes_bin}")

    profile_dir = _resolve_under(profile_root, profile, kind="profile")
    hermes_home = profile_dir / ".hermes"
    if not hermes_home.is_dir():
        raise SpawnRejected(
            "not_found", f"profile .hermes/ missing: {hermes_home}"
        )
    env_file = hermes_home / ".env"
    if not env_file.is_file():
        raise SpawnRejected(
            "not_found", f"profile .env missing: {env_file}"
        )

    workspace = _resolve_under(workspace_root, profile, kind="workspace")

    # Build a narrow, deterministic env. Order matters so subsequent
    # keys can override earlier ones where allowed.
    env: dict[str, str] = {
        "PATH": FIXED_PATH,
        "HOME": str(profile_dir),
        "HERMES_HOME": str(hermes_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    env.update(parse_env_file(env_file))

    argv: list[str] = [
        str(hermes_bin),
        "chat",
        "-Q",
        "--pass-session-id",
        "--source",
        "tool",
        "-q",
        prompt,
    ]
    if model:
        argv.extend(["-m", model])
    extra_list = list(extra_argv)
    if any(a.startswith("-q") or a == "--query" for a in extra_list):
        raise SpawnRejected(
            "bad_request", "extra_argv may not override -q/--query"
        )
    argv.extend(extra_list)

    return SpawnPlan(
        run_id=run_id,
        session_id=session_id,
        profile=profile,
        argv=tuple(argv),
        env=env,
        cwd=workspace,
        hermes_home=hermes_home,
        workspace=workspace,
    )


@dataclass
class SpawnHandle:
    """Live handle to a running Hermes subprocess.

    The app layer stores these in an in-memory registry keyed by
    ``plan.run_id`` so ``POST /runs/{id}/attach`` and
    ``POST /runs/{id}/cancel`` can reach back to the process.
    """

    plan: SpawnPlan
    process: subprocess.Popen[bytes]
    extra: dict[str, object] = field(default_factory=dict)


def execute_spawn(plan: SpawnPlan) -> SpawnHandle:
    """Fork the Hermes process described by ``plan``.

    stdout/stderr are merged into a pipe so attachers see interleaved
    output. stdin is closed (no interactive input). ``start_new_session``
    starts the child in its own process group so we can SIGTERM the
    whole group on cancel without killing the gateway.
    """

    process = subprocess.Popen(
        list(plan.argv),
        env=plan.env,
        cwd=str(plan.cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    return SpawnHandle(plan=plan, process=process)
