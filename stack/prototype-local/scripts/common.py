#!/usr/bin/env python3
"""Shared helpers for prototype-local bootstrap scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / "stack" / "prototype-local" / ".env"
COMPOSE_FILE = REPO_ROOT / "stack" / "prototype-local" / "docker-compose.substrate.yml"


def parse_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def compose_base_args() -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(ENV_PATH),
        "-f",
        str(COMPOSE_FILE),
    ]


def run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def compose_exec(service: str, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(compose_base_args() + ["exec", "-T", service, *command], check=check)


def compose_cp(source: Path, destination: str) -> subprocess.CompletedProcess[str]:
    return run(compose_base_args() + ["cp", str(source), destination], check=True)


def compose_restart(service: str) -> subprocess.CompletedProcess[str]:
    return run(compose_base_args() + ["restart", service], check=True)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"missing required command: {name}")


def wait_for_http(url: str, *, timeout: int = 120, interval: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except Exception:
            pass
        time.sleep(interval)
    raise SystemExit(f"timed out waiting for {url}")


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, object] | list[object] | None = None,
) -> dict[str, object] | list[object]:
    data = None
    req_headers = {"Content-Type": "application/json"}
    req_headers.update(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=req_headers)
    with request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)
