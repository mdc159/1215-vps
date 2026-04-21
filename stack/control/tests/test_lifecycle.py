"""Unit tests for control1215.lifecycle.

These never touch the real docker daemon or systemd. They stub out
``subprocess.run`` / ``curl_ok`` / ``unit_state`` to verify the command
composition and status-aggregation logic in isolation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from control1215 import lifecycle


# --- ServiceSpec / registry ------------------------------------------


def test_service_registry_has_expected_critical_entries() -> None:
    names = [s.name for s in lifecycle.SERVICES]
    for required in ("broker", "postgres", "minio", "honcho", "hermes-gateway", "paperclip"):
        assert required in names, f"registry missing {required}"


def test_get_service_raises_on_unknown() -> None:
    with pytest.raises(KeyError):
        lifecycle.get_service("nonexistent-service")


def test_resolve_socket_path_expands_percent_t(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    spec = lifecycle.get_service("hermes-gateway")
    resolved = lifecycle.resolve_socket_path(spec)
    assert resolved is not None
    assert str(resolved).startswith(str(tmp_path))
    assert resolved.name == "gateway.sock"


# --- exposure smoke test ---------------------------------------------


def test_exposure_smoke_test_accepts_loopback_only(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            args=a[0] if a else [],
            returncode=0,
            stdout=(
                "foo\t127.0.0.1:8090->8090/tcp\n"
                "bar\t[::1]:3000->3000/tcp\n"
            ),
            stderr="",
        ),
    )
    ok, msg = lifecycle.exposure_smoke_test()
    assert ok, msg


def test_exposure_smoke_test_flags_0_0_0_0(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            args=a[0] if a else [],
            returncode=0,
            stdout="leaky\t0.0.0.0:5678->5678/tcp\n",
            stderr="",
        ),
    )
    ok, msg = lifecycle.exposure_smoke_test()
    assert not ok
    assert "leaky" in msg


# --- canary check ----------------------------------------------------


def test_canary_check_clean_when_no_hits(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # Make target_env_file return a path without LANGFUSE creds so the
    # Langfuse branch is skipped; broker calls return empty payloads.
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=x\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "target_env_file", lambda _t: env_file)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, msg = lifecycle.canary_check("CANARY-XYZ")
    assert ok, msg


def test_canary_check_flags_broker_leak(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=x\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "target_env_file", lambda _t: env_file)

    def fake_run(argv, **kwargs):
        url = argv[-1] if argv else ""
        payload = (
            "{\"events\": [{\"payload_json\": \"CANARY-XYZ\"}]}"
            if "events" in url
            else "{}"
        )
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, msg = lifecycle.canary_check("CANARY-XYZ")
    assert not ok
    assert "broker /events" in msg


# --- collect_status --------------------------------------------------


def test_collect_status_marks_missing_compose_as_missing(monkeypatch) -> None:
    # No compose rows = every compose service is missing.
    monkeypatch.setattr(lifecycle, "compose_ps", lambda _t: [])
    # No user units running either.
    monkeypatch.setattr(lifecycle, "unit_state", lambda _n: ("", ""))
    monkeypatch.setattr(lifecycle, "curl_ok", lambda _u, **k: False)

    statuses = lifecycle.collect_status("prototype-local")
    by_name = {s.name: s for s in statuses}
    assert by_name["broker"].state == "missing"
    assert by_name["honcho"].state == "missing"


def test_collect_status_healthy_compose_row(monkeypatch) -> None:
    monkeypatch.setattr(
        lifecycle,
        "compose_ps",
        lambda _t: [
            {
                "Service": "broker",
                "State": "running",
                "Health": "healthy",
                "Image": "broker:prototype",
                "ID": "abc123",
            }
        ],
    )
    monkeypatch.setattr(lifecycle, "unit_state", lambda _n: ("active", "running"))
    monkeypatch.setattr(lifecycle, "curl_ok", lambda _u, **k: True)

    statuses = lifecycle.collect_status("prototype-local")
    by_name = {s.name: s for s in statuses}
    assert by_name["broker"].state == "up"
    assert by_name["broker"].health == "healthy"


def test_do_status_nonzero_when_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(lifecycle, "compose_ps", lambda _t: [])
    monkeypatch.setattr(lifecycle, "unit_state", lambda _n: ("", ""))
    monkeypatch.setattr(lifecycle, "curl_ok", lambda _u, **k: False)

    rc = lifecycle.do_status("prototype-local")
    assert rc == 1


def test_do_status_json_is_parseable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(lifecycle, "compose_ps", lambda _t: [])
    monkeypatch.setattr(lifecycle, "unit_state", lambda _n: ("", ""))
    monkeypatch.setattr(lifecycle, "curl_ok", lambda _u, **k: False)

    lifecycle.do_status("prototype-local", as_json=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert all("name" in row and "state" in row for row in parsed)


# --- format_status_table ---------------------------------------------


def test_format_status_table_headers_present() -> None:
    statuses = [
        lifecycle.ServiceStatus(
            name="broker",
            source="compose",
            state="up",
            health="healthy",
            port="8090",
            hint="—",
        )
    ]
    rendered = lifecycle.format_status_table(statuses)
    assert "NAME" in rendered
    assert "SOURCE" in rendered
    assert "broker" in rendered
