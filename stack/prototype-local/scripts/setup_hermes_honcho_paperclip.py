#!/usr/bin/env python3
"""Bring up Hermes + Paperclip on a local 1215 node.

As of Phase B, Honcho is no longer launched from here — it runs as a
systemd --user service (see stack/services/honcho/) against the shared
substrate Postgres. This script now only:

  - confirms Honcho is already healthy at http://127.0.0.1:18000/health
    (fail fast with a pointer to the install.sh otherwise),
  - configures Hermes on the host to use Honcho as its memory provider,
  - brings up the legacy host-docker Paperclip quickstart (Phase E will
    move Paperclip into the main compose file),
  - runs the Hermes ↔ Honcho memory write/read smoke test.

The separate 1215-honcho-pg Postgres container created by earlier
versions of this script has been retired; if it is still running on
this host, remove it manually (`docker rm -f 1215-honcho-pg`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib import request


REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_ENV_PATH = REPO_ROOT / "stack" / "prototype-local" / ".env"
HERMES_DIR = REPO_ROOT / "modules" / "hermes-agent"
PAPERCLIP_DOCKER_DIR = REPO_ROOT / "modules" / "paperclip" / "docker"

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


def wait_for_honcho() -> dict[str, object]:
    """Confirm the host-native Honcho (systemd --user) is healthy.

    Unlike earlier versions of this script, it does NOT start Honcho;
    that is managed by stack/services/honcho/honcho.service. Give a
    clear pointer back to the installer if the service isn't up.
    """
    try:
        return wait_http(HONCHO_HEALTH_URL, timeout=90)
    except SystemExit as exc:
        raise SystemExit(
            f"{exc}\n\nHoncho is expected to be running as a systemd --user service. "
            "Install and start it with:\n"
            "  bash stack/services/honcho/install.sh\n"
            "  systemctl --user enable --now honcho honcho-deriver"
        )


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

    honcho_info = {"health": wait_for_honcho()}
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
