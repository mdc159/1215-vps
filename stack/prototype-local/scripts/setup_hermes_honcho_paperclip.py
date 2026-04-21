#!/usr/bin/env python3
"""Bring up Hermes + self-hosted Honcho + Paperclip on a local 1215 node."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_ENV_PATH = REPO_ROOT / "stack" / "prototype-local" / ".env"
HONCHO_DIR = REPO_ROOT / "modules" / "honcho"
HERMES_DIR = REPO_ROOT / "modules" / "hermes-agent"
PAPERCLIP_DOCKER_DIR = REPO_ROOT / "modules" / "paperclip" / "docker"

HONCHO_PG_CONTAINER = "1215-honcho-pg"
HONCHO_RUNTIME_ENV_PATH = Path("/tmp/honcho-runtime.env")
HONCHO_API_LOG = Path("/tmp/honcho-api-persistent.log")
HONCHO_DERIVER_LOG = Path("/tmp/honcho-deriver-persistent.log")
HONCHO_API_PID = Path("/tmp/honcho-api.pid")
HONCHO_DERIVER_PID = Path("/tmp/honcho-deriver.pid")

HONCHO_HEALTH_URL = "http://127.0.0.1:18000/health"
PAPERCLIP_HEALTH_URL = "http://127.0.0.1:3100/api/health"


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def wait_http(url: str, timeout: int = 120) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8")
                if 200 <= response.status < 300:
                    return json.loads(body) if body else {}
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"timed out waiting for {url}")


def ensure_honcho_pgvector() -> None:
    names = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout.splitlines()
    if HONCHO_PG_CONTAINER not in names:
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                HONCHO_PG_CONTAINER,
                "-e",
                "POSTGRES_USER=honcho",
                "-e",
                "POSTGRES_PASSWORD=honcho",
                "-e",
                "POSTGRES_DB=honcho",
                "-p",
                "55432:5432",
                "pgvector/pgvector:pg17",
            ]
        )
    else:
        running = (
            run(["docker", "inspect", "-f", "{{.State.Running}}", HONCHO_PG_CONTAINER], check=False)
            .stdout.strip()
            .lower()
        )
        if running != "true":
            run(["docker", "start", HONCHO_PG_CONTAINER])

    for _ in range(60):
        probe = run(
            ["docker", "exec", HONCHO_PG_CONTAINER, "pg_isready", "-U", "honcho", "-d", "honcho"],
            check=False,
        )
        if probe.returncode == 0:
            break
        time.sleep(1)
    else:
        raise SystemExit("honcho pgvector container did not become ready")

    run(
        [
            "docker",
            "exec",
            HONCHO_PG_CONTAINER,
            "psql",
            "-U",
            "honcho",
            "-d",
            "honcho",
            "-c",
            "CREATE EXTENSION IF NOT EXISTS vector;",
        ]
    )


def build_honcho_runtime_env(openrouter_api_key: str) -> dict[str, str]:
    env = {
        "DB_CONNECTION_URI": "postgresql+psycopg://honcho:honcho@127.0.0.1:55432/honcho",
        "AUTH_USE_AUTH": "false",
        "LOG_LEVEL": "INFO",
        "VECTOR_STORE_TYPE": "pgvector",
        "LLM_OPENAI_COMPATIBLE_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_OPENAI_COMPATIBLE_API_KEY": openrouter_api_key,
        "LLM_EMBEDDING_PROVIDER": "openrouter",
        "DERIVER_PROVIDER": "custom",
        "DERIVER_MODEL": "openai/gpt-4o-mini",
        "SUMMARY_PROVIDER": "custom",
        "SUMMARY_MODEL": "openai/gpt-4o-mini",
        "DREAM_PROVIDER": "custom",
        "DREAM_MODEL": "openai/gpt-4o-mini",
        "DREAM_DEDUCTION_MODEL": "openai/gpt-4o-mini",
        "DREAM_INDUCTION_MODEL": "openai/gpt-4o-mini",
    }
    for level in ("minimal", "low", "medium", "high", "max"):
        env[f"DIALECTIC_LEVELS__{level}__PROVIDER"] = "custom"
        env[f"DIALECTIC_LEVELS__{level}__MODEL"] = "openai/gpt-4o-mini"
        env[f"DIALECTIC_LEVELS__{level}__THINKING_BUDGET_TOKENS"] = "0"
        env[f"DIALECTIC_LEVELS__{level}__MAX_TOOL_ITERATIONS"] = "1"
    return env


def write_runtime_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n")


def terminate_pidfile(path: Path) -> None:
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
    except Exception:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        pass


def start_honcho_services(runtime_env: dict[str, str]) -> dict[str, object]:
    write_runtime_env(HONCHO_RUNTIME_ENV_PATH, runtime_env)
    terminate_pidfile(HONCHO_API_PID)
    terminate_pidfile(HONCHO_DERIVER_PID)

    run(["uv", "sync"], cwd=HONCHO_DIR)

    migrate_env = os.environ.copy()
    migrate_env.update(runtime_env)
    run(["uv", "run", "alembic", "upgrade", "head"], cwd=HONCHO_DIR, env=migrate_env)

    api_cmd = (
        f"set -a; source {HONCHO_RUNTIME_ENV_PATH}; set +a; "
        "uv run fastapi run src/main.py --host 127.0.0.1 --port 18000"
    )
    deriver_cmd = (
        f"set -a; source {HONCHO_RUNTIME_ENV_PATH}; set +a; "
        "uv run python -m src.deriver"
    )
    with HONCHO_API_LOG.open("a") as api_log:
        api_proc = subprocess.Popen(
            ["bash", "-lc", api_cmd],
            cwd=str(HONCHO_DIR),
            stdout=api_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    with HONCHO_DERIVER_LOG.open("a") as deriver_log:
        deriver_proc = subprocess.Popen(
            ["bash", "-lc", deriver_cmd],
            cwd=str(HONCHO_DIR),
            stdout=deriver_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )

    HONCHO_API_PID.write_text(str(api_proc.pid))
    HONCHO_DERIVER_PID.write_text(str(deriver_proc.pid))

    health = wait_http(HONCHO_HEALTH_URL, timeout=90)
    return {"pid_api": api_proc.pid, "pid_deriver": deriver_proc.pid, "health": health}


def configure_hermes(openrouter_api_key: str, model: str) -> dict[str, object]:
    run(["uv", "sync"], cwd=HERMES_DIR)
    run(["uv", "pip", "install", "--python", ".venv/bin/python", "honcho-ai"], cwd=HERMES_DIR)

    hermes_home = Path.home() / ".hermes"
    hermes_home.mkdir(parents=True, exist_ok=True)
    honcho_cfg_path = hermes_home / "honcho.json"
    honcho_cfg: dict[str, object] = {}
    if honcho_cfg_path.exists():
        try:
            honcho_cfg = json.loads(honcho_cfg_path.read_text())
        except json.JSONDecodeError:
            honcho_cfg = {}
    honcho_cfg.update(
        {
            "baseUrl": "http://127.0.0.1:18000",
            "workspace": "1215-vps",
            "peerName": "user",
            "aiPeer": "hermes",
            "enabled": True,
            "recallMode": "hybrid",
            "writeFrequency": "turn",
            "contextCadence": 1,
            "dialecticCadence": 1,
        }
    )
    honcho_cfg_path.write_text(json.dumps(honcho_cfg, indent=2) + "\n")

    run([".venv/bin/hermes", "config", "set", "memory.provider", "honcho"], cwd=HERMES_DIR)
    run([".venv/bin/hermes", "config", "set", "model", model], cwd=HERMES_DIR)

    status = run([".venv/bin/hermes", "memory", "status"], cwd=HERMES_DIR).stdout
    return {"memory_status": status, "openrouter_key_present": bool(openrouter_api_key)}


def start_paperclip(openrouter_api_key: str, data_dir: Path, auth_secret: str) -> dict[str, object]:
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(data_dir, 0o777)

    env = os.environ.copy()
    env.update(
        {
            "OPENAI_API_KEY": openrouter_api_key,
            "BETTER_AUTH_SECRET": auth_secret,
            "PAPERCLIP_DATA_DIR": str(data_dir),
        }
    )

    run(
        ["docker", "compose", "-f", "docker-compose.quickstart.yml", "down"],
        cwd=PAPERCLIP_DOCKER_DIR,
        env=env,
        check=False,
    )
    run(["docker", "compose", "-f", "docker-compose.quickstart.yml", "up", "-d"], cwd=PAPERCLIP_DOCKER_DIR, env=env)
    health = wait_http(PAPERCLIP_HEALTH_URL, timeout=180)
    return {"health": health}


def run_memory_smoke(openrouter_api_key: str, token: str) -> dict[str, object]:
    env = os.environ.copy()
    env.update(
        {
            "OPENROUTER_API_KEY": openrouter_api_key,
            "HONCHO_BASE_URL": "http://127.0.0.1:18000",
        }
    )
    write_prompt = (
        "Use honcho_conclude to store exactly this fact about the user: "
        f"'Proof token is {token}'. Then confirm done in one line."
    )
    read_prompt = "Use honcho_search and tell me the proof token in one line."
    write_result: subprocess.CompletedProcess[str] | None = None
    read_result: subprocess.CompletedProcess[str] | None = None
    for _ in range(3):
        write_result = run(
            [".venv/bin/hermes", "chat", "-q", write_prompt],
            cwd=HERMES_DIR,
            env=env,
            check=False,
        )
        if write_result.returncode == 0:
            break
        time.sleep(1)
    for _ in range(3):
        read_result = run(
            [".venv/bin/hermes", "chat", "-q", read_prompt],
            cwd=HERMES_DIR,
            env=env,
            check=False,
        )
        if read_result.returncode == 0:
            break
        time.sleep(1)

    assert write_result is not None
    assert read_result is not None
    write_out = write_result.stdout + write_result.stderr
    read_out = read_result.stdout + read_result.stderr
    if write_result.returncode != 0 or read_result.returncode != 0:
        raise SystemExit(
            "Hermes/Honcho smoke test command failure:\n"
            f"write_rc={write_result.returncode}\n"
            f"read_rc={read_result.returncode}\n"
            f"write_tail={write_out[-1200:]}\n"
            f"read_tail={read_out[-1200:]}"
        )
    ok = token in write_out and token in read_out
    if not ok:
        raise SystemExit("Hermes/Honcho smoke test failed: token not found in write/read output")
    return {"token": token, "write_contains_token": token in write_out, "read_contains_token": token in read_out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="openai/gpt-4o-mini", help="Hermes model ID (OpenRouter format).")
    parser.add_argument("--paperclip-data-dir", default="/tmp/paperclip-data-1215", help="Writable host directory for Paperclip data volume.")
    parser.add_argument("--paperclip-auth-secret", default="paperclip-local-secret-1215", help="BETTER_AUTH_SECRET value for local Paperclip.")
    parser.add_argument("--smoke-token", default="HERMES_PROOF_18000", help="Token used by the Hermes/Honcho smoke memory test.")
    parser.add_argument("--skip-smoke-test", action="store_true", help="Skip Hermes/Honcho write-read smoke test.")
    args = parser.parse_args()

    if not LOCAL_ENV_PATH.exists():
        raise SystemExit(f"missing env file: {LOCAL_ENV_PATH}")
    local_env = parse_env(LOCAL_ENV_PATH)
    openrouter_api_key = local_env.get("OPENROUTER_API_KEY", "").strip()
    if not openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is empty in stack/prototype-local/.env")

    ensure_honcho_pgvector()
    honcho_info = start_honcho_services(build_honcho_runtime_env(openrouter_api_key))
    hermes_info = configure_hermes(openrouter_api_key, args.model)
    paperclip_info = start_paperclip(openrouter_api_key, Path(args.paperclip_data_dir), args.paperclip_auth_secret)

    smoke_info: dict[str, object] | None = None
    if not args.skip_smoke_test:
        smoke_info = run_memory_smoke(openrouter_api_key, args.smoke_token)

    summary = {
        "honcho": honcho_info,
        "paperclip": paperclip_info,
        "hermes_model": args.model,
        "hermes_memory_provider": "honcho",
        "smoke_test": smoke_info,
        "endpoints": {
            "honcho_health": HONCHO_HEALTH_URL,
            "paperclip_health": PAPERCLIP_HEALTH_URL,
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
