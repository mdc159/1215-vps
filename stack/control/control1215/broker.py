from __future__ import annotations

import subprocess
from pathlib import Path

from .compose import docker_compose_args
from .topology import resolve_paths


def broker_sql_dir() -> Path:
    return resolve_paths().stack_root / "sql" / "broker"


def broker_sql_files() -> list[Path]:
    return sorted(broker_sql_dir().glob("*.sql"))


def render_broker_sql() -> str:
    chunks: list[str] = []
    for path in broker_sql_files():
        chunks.append(f"-- {path.name}\n")
        chunks.append(path.read_text(encoding="utf-8").rstrip())
        chunks.append("\n")
    return "\n".join(chunks).strip() + "\n"


def apply_broker_sql(target_name: str) -> subprocess.CompletedProcess[str]:
    command = docker_compose_args(
        target_name,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        "-",
    )
    return subprocess.run(
        command,
        input=render_broker_sql(),
        text=True,
        capture_output=True,
        check=False,
    )
