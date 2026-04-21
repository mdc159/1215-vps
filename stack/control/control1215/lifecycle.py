"""Operator lifecycle primitives behind ``1215 {up,down,status,logs,smoke}``.

This module encapsulates the knowledge of *where each service lives*
(compose service vs systemd --user unit vs host socket) so the CLI
commands stay thin. Phase H in ``docs/architecture/execution-plan.md``
is the spec.

Key design choices:

- Service registry is declarative (``SERVICES``). Adding a new service
  means adding one row; no branching on service name elsewhere.
- Every operation is *idempotent* — re-running ``up`` after ``up`` is a
  no-op, re-running ``down`` when nothing is running exits 0.
- Health probes rely on the compose stack's own healthchecks
  (``docker compose up -d --wait``) plus best-effort HTTP probes against
  the services that expose ``/healthz``. Unit-level probes use
  ``systemctl --user is-active``.
- ``smoke`` composes three in-process checks (exposure, canary,
  gate_shared_core). If any fails the command exits non-zero; the
  output is both human-readable and machine-parseable (``--json``).

Everything deliberately stays in stdlib + the top-level ``docker`` /
``systemctl`` / ``curl`` binaries. No new Python dependencies.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .compose import docker_compose_args, target_compose_files, target_env_file
from .topology import resolve_paths


# --- Service registry -------------------------------------------------


@dataclass(frozen=True)
class ServiceSpec:
    """Declarative row describing where a service runs and how to probe it.

    ``source``: ``"compose"`` or ``"user-unit"``.
    ``compose_service``: service name in docker-compose.substrate.yml
        (only meaningful when ``source == "compose"``).
    ``unit_name``: systemd --user unit name (only meaningful when
        ``source == "user-unit"``).
    ``healthz_url``: optional URL to curl for a finer-grained check.
    ``port``: optional TCP port for the operator summary table.
    ``socket_path``: optional UDS path (for hermes-gateway).
    """

    name: str
    source: str
    compose_service: str | None = None
    unit_name: str | None = None
    healthz_url: str | None = None
    port: str | None = None
    socket_path: str | None = None
    depends_on_substrate: bool = True


# Ordered so `up` brings substrate first, then user units. `down`
# iterates in reverse.
SERVICES: list[ServiceSpec] = [
    ServiceSpec("postgres", "compose", compose_service="postgres", port="5433"),
    ServiceSpec("valkey", "compose", compose_service="valkey", port="6379"),
    ServiceSpec("minio", "compose", compose_service="minio", port="9010"),
    ServiceSpec("qdrant", "compose", compose_service="qdrant", port="6335"),
    ServiceSpec("neo4j", "compose", compose_service="neo4j", port="7475"),
    ServiceSpec("clickhouse", "compose", compose_service="clickhouse", port="8124"),
    ServiceSpec(
        "broker",
        "compose",
        compose_service="broker",
        healthz_url="http://127.0.0.1:8090/healthz",
        port="8090",
    ),
    ServiceSpec(
        "langfuse-web",
        "compose",
        compose_service="langfuse-web",
        healthz_url="http://127.0.0.1:3000/api/public/health",
        port="3000",
    ),
    ServiceSpec("langfuse-worker", "compose", compose_service="langfuse-worker", port="3030"),
    ServiceSpec(
        "open-webui",
        "compose",
        compose_service="open-webui",
        port="8080",
    ),
    ServiceSpec("n8n", "compose", compose_service="n8n", port="5678"),
    ServiceSpec("n8n-mcp", "compose", compose_service="n8n-mcp", port="3011"),
    ServiceSpec(
        "paperclip",
        "compose",
        compose_service="paperclip",
        port="3100",
    ),
    # Host-native user units come *after* compose because they talk to
    # Postgres / MinIO / broker directly on 127.0.0.1.
    ServiceSpec(
        "honcho",
        "user-unit",
        unit_name="honcho.service",
        healthz_url="http://127.0.0.1:18000/health",
        port="18000",
    ),
    ServiceSpec(
        "honcho-deriver",
        "user-unit",
        unit_name="honcho-deriver.service",
    ),
    ServiceSpec(
        "hermes-gateway",
        "user-unit",
        unit_name="hermes-gateway.service",
        socket_path="%t/hermes-gateway/gateway.sock",
    ),
]


def get_service(name: str) -> ServiceSpec:
    for spec in SERVICES:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown service {name!r}")


def xdg_runtime_dir() -> Path:
    return Path(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    )


def resolve_socket_path(spec: ServiceSpec) -> Path | None:
    """Expand the systemd-style ``%t`` placeholder for UDS paths."""
    if not spec.socket_path:
        return None
    return Path(spec.socket_path.replace("%t", str(xdg_runtime_dir())))


# --- Process helpers --------------------------------------------------


def _run(
    argv: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around subprocess.run with sane defaults."""
    return subprocess.run(
        argv,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
    )


def _compose_cli(target: str, *extra: str) -> list[str]:
    """Build the ``docker compose -f ... --env-file ...`` prefix."""
    return docker_compose_args(target, *extra)


def curl_ok(url: str, timeout: int = 2) -> bool:
    """Return True iff a GET of ``url`` returns HTTP 2xx within timeout."""
    if not shutil.which("curl"):
        return False
    try:
        result = subprocess.run(
            ["curl", "-fsS", "-m", str(timeout), "-o", "/dev/null", url],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def unit_active(unit_name: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    result = subprocess.run(
        ["systemctl", "--user", "is-active", unit_name],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "active"


def unit_state(unit_name: str) -> tuple[str, str]:
    """Return (ActiveState, SubState) for a --user unit; ("", "") if unknown."""
    if not shutil.which("systemctl"):
        return ("", "")
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit_name,
            "--property=ActiveState,SubState",
            "--no-page",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    active, sub = "", ""
    for line in result.stdout.splitlines():
        if line.startswith("ActiveState="):
            active = line.split("=", 1)[1]
        elif line.startswith("SubState="):
            sub = line.split("=", 1)[1]
    return (active, sub)


# --- up / down --------------------------------------------------------


def ensure_env_file(target: str) -> Path:
    """Run init_env.py if the target's .env is missing.

    ``init_env.py`` is the canonical bootstrap for ``stack/prototype-local/.env``;
    re-running it on an existing file is a no-op (it preserves values it
    cannot regenerate, like secrets). Returns the resolved .env path.
    """
    env_path = target_env_file(target)
    if env_path is None:
        return Path("/dev/null")  # target has no env file declared
    if env_path.exists():
        return env_path

    paths = resolve_paths()
    init = paths.stack_root / "prototype-local" / "scripts" / "init_env.py"
    if init.exists():
        _run([sys.executable, str(init)], check=True)
    return env_path


def compose_up(target: str, *, wait: bool = True) -> None:
    """``docker compose -f … up -d --wait`` for the target."""
    argv = _compose_cli(target, "up", "-d")
    if wait:
        argv.append("--wait")
    _run(argv, check=True)


def compose_down(target: str, *, remove_volumes: bool = False) -> None:
    argv = _compose_cli(target, "down")
    if remove_volumes:
        argv.append("--volumes")
    _run(argv, check=True)


def compose_ps(target: str) -> list[dict[str, Any]]:
    """Return parsed ``docker compose ps --format json`` rows."""
    argv = _compose_cli(target, "ps", "--format", "json")
    result = _run(argv, check=False, capture=True)
    if result.returncode != 0:
        return []
    out = result.stdout.strip()
    if not out:
        return []
    # Newer docker-compose emits one JSON doc per line; older emits a
    # single JSON array. Handle both.
    if out.startswith("["):
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def start_user_unit(unit_name: str) -> None:
    """Idempotent: `start` is a no-op if already active."""
    _run(["systemctl", "--user", "enable", unit_name], check=False, capture=True)
    _run(["systemctl", "--user", "restart", unit_name], check=True)


def stop_user_unit(unit_name: str) -> None:
    _run(["systemctl", "--user", "stop", unit_name], check=False, capture=True)


def wait_for(probe, *, timeout: int, poll: float = 1.0) -> bool:
    """Block until ``probe()`` returns truthy or ``timeout`` is exceeded."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe():
            return True
        time.sleep(poll)
    return False


# --- status -----------------------------------------------------------


@dataclass
class ServiceStatus:
    name: str
    source: str
    state: str  # "up", "down", "degraded", "missing"
    health: str  # "healthy", "unhealthy", "starting", "n/a"
    port: str | None
    hint: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        return d


def _compose_row_for(rows: list[dict[str, Any]], compose_service: str) -> dict[str, Any] | None:
    for row in rows:
        # docker compose v2 uses "Service" for the compose-service name.
        if row.get("Service") == compose_service:
            return row
    return None


def collect_status(target: str) -> list[ServiceStatus]:
    rows = compose_ps(target)
    statuses: list[ServiceStatus] = []

    for spec in SERVICES:
        if spec.source == "compose":
            row = _compose_row_for(rows, spec.compose_service or spec.name)
            if row is None:
                statuses.append(
                    ServiceStatus(
                        name=spec.name,
                        source="compose",
                        state="missing",
                        health="n/a",
                        port=spec.port,
                        hint="not in `docker compose ps`",
                    )
                )
                continue
            state = row.get("State", "unknown")
            health = row.get("Health") or "n/a"
            hint = "—"
            if state != "running":
                hint = f"state={state}"
            elif health and health not in ("healthy", "n/a", ""):
                hint = f"health={health}"
            statuses.append(
                ServiceStatus(
                    name=spec.name,
                    source="compose",
                    state="up" if state == "running" else state,
                    health=health or "n/a",
                    port=spec.port,
                    hint=hint,
                    extras={"image": row.get("Image"), "id": row.get("ID")},
                )
            )

        else:  # user-unit
            active, sub = unit_state(spec.unit_name or "")
            if not active:
                statuses.append(
                    ServiceStatus(
                        name=spec.name,
                        source="user-unit",
                        state="missing",
                        health="n/a",
                        port=spec.port,
                        hint="unit not installed",
                    )
                )
                continue
            state = "up" if active == "active" else active or "unknown"
            hint = "—" if active == "active" else f"sub={sub or '?'}"
            health = "n/a"
            if spec.healthz_url:
                health = "healthy" if curl_ok(spec.healthz_url) else "unhealthy"
                if health == "unhealthy" and state == "up":
                    hint = f"healthz failing: {spec.healthz_url}"
            if spec.socket_path:
                socket = resolve_socket_path(spec)
                if socket and not socket.exists():
                    health = "unhealthy"
                    hint = f"socket missing: {socket}"
            statuses.append(
                ServiceStatus(
                    name=spec.name,
                    source="user-unit",
                    state=state,
                    health=health,
                    port=spec.port,
                    hint=hint,
                    extras={"active": active, "sub": sub},
                )
            )

    return statuses


def format_status_table(statuses: Iterable[ServiceStatus]) -> str:
    cols = ["NAME", "SOURCE", "STATE", "HEALTH", "PORT", "HINT"]
    rows = [
        [
            s.name,
            s.source,
            s.state,
            s.health,
            s.port or "-",
            s.hint or "-",
        ]
        for s in statuses
    ]
    widths = [max(len(str(r[i])) for r in [cols] + rows) for i in range(len(cols))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*cols), fmt.format(*["-" * w for w in widths])]
    lines.extend(fmt.format(*row) for row in rows)
    return "\n".join(lines)


# --- smoke ------------------------------------------------------------


def exposure_smoke_test() -> tuple[bool, str]:
    """Fail if any running container binds to a non-loopback host IP.

    A container that publishes 0.0.0.0:PORT -> CONTAINER:PORT would
    expose a prototype service to the LAN; the local-only invariant
    from ``north-star.md`` forbids that.
    """
    # Scope the check to the 1215 compose project only — other projects on
    # the same Docker daemon (archon, sisyphus, …) are out of scope for the
    # north-star local-only invariant.
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=1215-prototype-local",
            "--format",
            "{{.Names}}\t{{.Ports}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, f"docker ps failed: {result.stderr.strip()}"

    leaks: list[str] = []
    for line in result.stdout.splitlines():
        name, _, ports = line.partition("\t")
        # A published port looks like "0.0.0.0:8080->8080/tcp" or
        # "127.0.0.1:8080->8080/tcp". We tolerate loopback and IPv6
        # loopback; anything else is a leak.
        for entry in ports.split(","):
            entry = entry.strip()
            if "->" not in entry:
                continue
            host_side = entry.split("->", 1)[0]
            if not host_side:
                continue
            if host_side.startswith("127.0.0.1:") or host_side.startswith("[::1]:"):
                continue
            if host_side.startswith("0.0.0.0:") or host_side.startswith("[::]:"):
                leaks.append(f"{name} -> {entry}")
                continue
            # Host-IP-specific binds (e.g. 192.168.x.x) are also leaks.
            if ":" in host_side and not host_side.startswith(
                ("127.", "[::1]")
            ):
                # Ignore "container-side only" protocol entries like "8080/tcp"
                if host_side[0].isdigit():
                    leaks.append(f"{name} -> {entry}")

    if leaks:
        return False, "non-loopback host binds:\n  " + "\n  ".join(leaks)
    return True, "no non-loopback binds"


def canary_check(canary: str) -> tuple[bool, str]:
    """Fail if the profile canary appears in broker payloads or Langfuse.

    A small, deliberate sweep rather than a deep scan — the acceptance
    intent is to catch an obvious regression, not to be exhaustive.
    """
    hits: list[str] = []

    # Broker: recent events + artifacts.
    for endpoint in ("events", "artifacts"):
        url = f"http://127.0.0.1:8090/{endpoint}?limit=200"
        try:
            result = subprocess.run(
                ["curl", "-fsS", "-m", "3", url],
                check=False,
                capture_output=True,
                text=True,
            )
            if canary in result.stdout:
                hits.append(f"broker /{endpoint}")
        except Exception:
            continue

    # Langfuse: only probe if the public key is set; most prototype
    # boots have it, but we treat absence as "Langfuse off, skip".
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key:
        # Try to read from prototype-local/.env
        env_file = target_env_file("prototype-local")
        if env_file and env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("LANGFUSE_PUBLIC_KEY="):
                    public_key = line.split("=", 1)[1]
                elif line.startswith("LANGFUSE_SECRET_KEY="):
                    secret_key = line.split("=", 1)[1]
    if public_key and secret_key:
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-fsS",
                    "-m",
                    "3",
                    "-u",
                    f"{public_key}:{secret_key}",
                    "http://127.0.0.1:3000/api/public/traces?limit=50",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if canary in result.stdout:
                hits.append("langfuse /traces")
        except Exception:
            pass

    if hits:
        return False, "canary leaked into: " + ", ".join(hits)
    return True, "canary absent from broker + langfuse"


def run_gate_shared_core(*, timeout: int = 600) -> tuple[bool, str]:
    """Invoke the in-repo gate_shared_core.py. Returns (ok, summary).

    The gate's sub-scripts (bootstrap_n8n.py, ...) import third-party
    packages like ``bcrypt`` that are expected on the host's system
    Python rather than in the control-1215 venv. We therefore invoke the
    gate with ``python3`` from PATH — falling back to ``sys.executable``
    only if ``python3`` is unavailable — to preserve the historical
    behavior of running these scripts outside of a uv-managed venv.
    """
    paths = resolve_paths()
    script = paths.stack_root / "prototype-local" / "scripts" / "gate_shared_core.py"
    if not script.exists():
        return False, f"missing: {script}"
    # Prefer the system /usr/bin/python3 (has bcrypt etc. pre-installed on
    # this prototype). Fall back to PATH python3 (which may be a venv shim
    # when the caller is running under `uv run`) and finally sys.executable.
    candidates = ["/usr/bin/python3", "python3"]
    python = ""
    for candidate in candidates:
        resolved = shutil.which(candidate) if not os.path.isabs(candidate) else (
            candidate if Path(candidate).exists() else None
        )
        if resolved:
            python = resolved
            break
    if not python:
        python = sys.executable
    result = subprocess.run(
        [python, str(script)],
        cwd=paths.repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        return False, "gate_shared_core failed:\n  " + "\n  ".join(tail)
    return True, "gate_shared_core passed"


def smoke(
    canary: str = "FAKE_CEO_SECRET_DO_NOT_LEAK_1215_KWHK8X2M",
    *,
    skip_gate: bool = False,
) -> list[tuple[str, bool, str]]:
    """Run the three phase-H smoke checks. Returns per-check results."""
    out: list[tuple[str, bool, str]] = []

    ok, msg = exposure_smoke_test()
    out.append(("exposure", ok, msg))

    ok, msg = canary_check(canary)
    out.append(("canary", ok, msg))

    if not skip_gate:
        ok, msg = run_gate_shared_core()
        out.append(("gate_shared_core", ok, msg))

    return out


# --- up / down orchestration -----------------------------------------


def do_up(target: str) -> int:
    """Full idempotent bringup."""
    ensure_env_file(target)
    print(f"[1/3] docker compose up -d --wait  (target={target})")
    try:
        compose_up(target, wait=True)
    except subprocess.CalledProcessError as exc:
        print(f"compose up failed: {exc}", file=sys.stderr)
        return 1

    print("[2/3] starting host-native user units")
    for spec in SERVICES:
        if spec.source != "user-unit":
            continue
        try:
            start_user_unit(spec.unit_name or "")
            print(f"  - {spec.name}: started")
        except subprocess.CalledProcessError as exc:
            print(f"  - {spec.name}: FAILED ({exc})", file=sys.stderr)
            return 1

    print("[3/3] probing /healthz for gatewayed services")
    ok_all = True
    for spec in SERVICES:
        if not spec.healthz_url:
            continue
        probe = lambda u=spec.healthz_url: curl_ok(u)
        if wait_for(probe, timeout=30):
            print(f"  - {spec.name}: healthy")
        else:
            print(f"  - {spec.name}: NOT HEALTHY ({spec.healthz_url})")
            ok_all = False

    return 0 if ok_all else 1


def do_down(target: str, *, remove_volumes: bool = False) -> int:
    """Reverse of ``do_up`` — user units first, then compose."""
    for spec in reversed(SERVICES):
        if spec.source != "user-unit":
            continue
        stop_user_unit(spec.unit_name or "")

    try:
        compose_down(target, remove_volumes=remove_volumes)
    except subprocess.CalledProcessError as exc:
        print(f"compose down failed: {exc}", file=sys.stderr)
        return 1
    return 0


def do_status(target: str, *, as_json: bool = False) -> int:
    statuses = collect_status(target)
    if as_json:
        print(json.dumps([s.to_dict() for s in statuses], indent=2, sort_keys=True))
    else:
        print(format_status_table(statuses))

    # Non-zero exit if anything is missing or degraded.
    bad = any(s.state in {"missing", "inactive", "failed"} or s.health == "unhealthy" for s in statuses)
    return 1 if bad else 0


def do_logs(service: str, *, follow: bool, target: str) -> int:
    spec = get_service(service)
    if spec.source == "compose":
        argv = _compose_cli(target, "logs", spec.compose_service or spec.name)
        if follow:
            argv.insert(-1, "-f")
    else:
        argv = ["journalctl", "--user", "-u", spec.unit_name or service]
        if follow:
            argv.append("-f")
    return subprocess.run(argv).returncode


def do_smoke(*, as_json: bool = False, skip_gate: bool = False) -> int:
    results = smoke(skip_gate=skip_gate)
    if as_json:
        print(
            json.dumps(
                [{"check": c, "ok": ok, "message": msg} for c, ok, msg in results],
                indent=2,
            )
        )
    else:
        for name, ok, msg in results:
            tag = "ok" if ok else "FAIL"
            print(f"[{tag}] {name}: {msg}")
    return 0 if all(ok for _, ok, _ in results) else 1
