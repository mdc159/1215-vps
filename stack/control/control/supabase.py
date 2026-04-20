"""Three-level readiness gate for Supabase."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol


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
