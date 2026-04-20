"""Phase 1 bring-up for the data plane."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from control import compose, envfile, supabase

log = logging.getLogger(__name__)

PROJECT = "localai"
REPO_ROOT = Path(__file__).resolve().parents[3]
LAI_ROOT = REPO_ROOT / "modules" / "local-ai-packaged"
LAI_COMPOSE = LAI_ROOT / "docker-compose.yml"
SUPABASE_COMPOSE = LAI_ROOT / "supabase" / "docker" / "docker-compose.yml"
OVERLAY_COMPOSE = REPO_ROOT / "stack" / "docker-compose.1215.yml"


def compose_files() -> list[Path]:
    """Return the compose files used for the Phase 1 stack."""
    return [LAI_COMPOSE, OVERLAY_COMPOSE]


def ensure_layout() -> None:
    """Validate upstream checkout state before invoking Compose."""
    missing = [str(path) for path in (LAI_COMPOSE, OVERLAY_COMPOSE) if not path.exists()]
    if not SUPABASE_COMPOSE.exists():
        missing.append(
            f"{SUPABASE_COMPOSE} (run modules/local-ai-packaged/start_services.py once "
            "or sparse-clone the upstream Supabase docker tree)"
        )
    if missing:
        raise FileNotFoundError("missing Phase 1 compose inputs:\n- " + "\n- ".join(missing))


def sync_upstream_env(env_path: Path) -> None:
    """Copy the rendered root env into the Local AI Package locations it expects."""
    ensure_layout()
    targets = [
        LAI_ROOT / ".env",
        SUPABASE_COMPOSE.parent / ".env",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(env_path, target)


def bring_up(
    *,
    env_path: Path,
    first_boot: bool,
    ollama_profile: str = "none",
    gate_timeout_s: float | None = None,
) -> None:
    """Bring up Phase 1 services and block on the Supabase readiness gate."""
    ensure_layout()
    sync_upstream_env(env_path)

    if gate_timeout_s is None:
        gate_timeout_s = 600.0 if first_boot else 120.0

    merged_env = envfile.parse(env_path)

    log.info("phase 1: starting data plane (%s)", ollama_profile)
    subcommand = ["up", "-d"]
    if ollama_profile != "none":
        subcommand = ["--profile", ollama_profile, *subcommand]
    compose.run(
        PROJECT,
        compose_files(),
        subcommand,
        cwd=REPO_ROOT,
        env=merged_env,
    )

    log.info("phase 1: waiting on Supabase readiness (timeout %.0fs)", gate_timeout_s)
    supabase.wait_for_supabase(
        supabase.default_checks(),
        timeout_s=gate_timeout_s,
    )

    for service in ("db-init", "mc-init"):
        log.info("phase 1: running %s", service)
        compose.run(
            PROJECT,
            compose_files(),
            ["up", "--no-deps", "--exit-code-from", service, service],
            cwd=REPO_ROOT,
            env=merged_env,
        )
