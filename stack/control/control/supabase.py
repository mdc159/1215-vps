"""Three-level readiness gate for Supabase."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import requests


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _WallClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class Checks:
    """Callables that return True when the level's condition is met."""

    container_healthy: Callable[[], bool]
    accepts_queries: Callable[[], bool]
    http_ready: Callable[[], bool]


def wait_for_supabase(
    checks: Checks,
    timeout_s: float,
    *,
    poll_interval_s: float = 3.0,
    clock: Clock | None = None,
) -> None:
    """Block until all three levels succeed, or raise TimeoutError."""
    active_clock = clock or _WallClock()
    deadline = active_clock.now() + timeout_s
    levels = [
        ("level 1 (container healthy)", checks.container_healthy),
        ("level 2 (psql SELECT 1)", checks.accepts_queries),
        ("level 3 (kong /auth/v1/health)", checks.http_ready),
    ]

    for name, probe in levels:
        while True:
            if probe():
                break
            if active_clock.now() >= deadline:
                raise TimeoutError(f"Supabase readiness {name} timed out")
            active_clock.sleep(poll_interval_s)


def probe_container_healthy(container_name: str = "supabase-db") -> bool:
    """Level 1: docker inspect says the container health is healthy."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "healthy"


def probe_accepts_queries(container_name: str = "supabase-db") -> bool:
    """Level 2: psql inside the container returns `1` for SELECT 1."""
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "psql",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-tAc",
                "SELECT 1",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "1"


def probe_http_ready(kong_url: str = "http://localhost:8000") -> bool:
    """Level 3: kong can route to the auth service."""
    try:
        response = requests.get(f"{kong_url}/auth/v1/health", timeout=5)
    except requests.RequestException:
        return False
    return 200 <= response.status_code < 500


def default_checks() -> Checks:
    return Checks(
        container_healthy=probe_container_healthy,
        accepts_queries=probe_accepts_queries,
        http_ready=probe_http_ready,
    )
