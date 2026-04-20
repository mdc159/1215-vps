"""End-to-end Phase 1 integration test."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from control import cli, compose, envfile
from control.phases import data_plane, preflight

pytestmark = pytest.mark.integration

PROJECT = "localai-test"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _docker_ready() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _service_container(project: str, service: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        compose.build_command(project, data_plane.compose_files(), ["ps", "-q", service]),
        cwd=data_plane.REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def sandboxed_env(tmp_path_factory):
    if not _docker_ready():
        pytest.skip("docker daemon is not reachable")
    if not data_plane.SUPABASE_COMPOSE.exists():
        pytest.skip(f"missing upstream Supabase checkout at {data_plane.SUPABASE_COMPOSE}")

    env_dir = tmp_path_factory.mktemp("env")
    shutil.copy(REPO_ROOT / "stack" / "env" / ".env.example", env_dir / ".env.example")
    return env_dir


@pytest.fixture(scope="module")
def populated_env(sandboxed_env):
    preflight.ensure_env(
        env_path=sandboxed_env / ".env",
        example_path=sandboxed_env / ".env.example",
        required=cli.PHASE1_REQUIRED,
        composed=cli.PHASE1_COMPOSED,
    )
    return sandboxed_env / ".env"


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    patcher = MonkeyPatch()
    yield patcher
    patcher.undo()


@pytest.fixture(scope="module")
def brought_up(populated_env, monkeypatch_module):
    monkeypatch_module.setattr(data_plane, "PROJECT", PROJECT)
    values = envfile.parse(populated_env)

    try:
        data_plane.bring_up(
            env_path=populated_env,
            first_boot=True,
            gate_timeout_s=600.0,
        )
        yield values
    finally:
        subprocess.run(
            compose.build_command(PROJECT, data_plane.compose_files(), ["down", "-v"]),
            cwd=data_plane.REPO_ROOT,
            env={**os.environ, **values},
            capture_output=True,
            text=True,
            check=False,
        )


def test_honcho_database_exists(brought_up):
    container = _service_container(PROJECT, "db", brought_up)
    assert container, "expected db container id from docker compose ps -q db"

    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "honcho",
            "-tAc",
            "SELECT count(*) FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": brought_up["POSTGRES_PASSWORD"]},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2", result.stdout


def test_broker_schema_and_tables_exist(brought_up):
    container = _service_container(PROJECT, "db", brought_up)
    assert container, "expected db container id from docker compose ps -q db"

    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            (
                "SELECT count(*) "
                "FROM information_schema.tables "
                "WHERE table_schema = 'broker' "
                "AND table_name IN ('alignment_log', 'artifact_manifests')"
            ),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": brought_up["POSTGRES_PASSWORD"]},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2", result.stdout


def test_minio_buckets_exist(brought_up):
    container = _service_container(PROJECT, "minio", brought_up)
    assert container, "expected minio container id from docker compose ps -q minio"

    result = subprocess.run(
        ["docker", "exec", container, "sh", "-c", "ls /data"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    names = set(result.stdout.split())
    assert {"artifacts", "langfuse", "n8n"}.issubset(names), names
