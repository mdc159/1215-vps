"""Tests for the three-level Supabase readiness gate."""
from __future__ import annotations

import pytest

from control import supabase


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_wait_passes_when_all_levels_succeed_immediately():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: True,
        http_ready=lambda: True,
    )
    supabase.wait_for_supabase(checks, timeout_s=10, clock=clock)


def test_wait_raises_when_level1_never_becomes_healthy():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: False,
        accepts_queries=lambda: True,
        http_ready=lambda: True,
    )
    with pytest.raises(TimeoutError, match="level 1"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_raises_when_level2_never_succeeds():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: False,
        http_ready=lambda: True,
    )
    with pytest.raises(TimeoutError, match="level 2"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_raises_when_level3_never_succeeds():
    clock = FakeClock()
    checks = supabase.Checks(
        container_healthy=lambda: True,
        accepts_queries=lambda: True,
        http_ready=lambda: False,
    )
    with pytest.raises(TimeoutError, match="level 3"):
        supabase.wait_for_supabase(checks, timeout_s=5, clock=clock)


def test_wait_progresses_through_levels():
    clock = FakeClock()
    level2_calls: list[float] = []

    def level1() -> bool:
        return clock.now() >= 3.0

    def level2() -> bool:
        level2_calls.append(clock.now())
        return True

    checks = supabase.Checks(
        container_healthy=level1,
        accepts_queries=level2,
        http_ready=lambda: True,
    )
    supabase.wait_for_supabase(checks, timeout_s=20, clock=clock)
    assert level2_calls
    for call_time in level2_calls:
        assert call_time >= 3.0, f"level 2 polled at t={call_time}"
