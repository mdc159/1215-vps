"""Phase 2 bring-up for self-hosted Honcho."""
from __future__ import annotations

from pathlib import Path

from control import compose, envfile, honcho
from control.phases import data_plane

REPO_ROOT = data_plane.REPO_ROOT
HONCHO_ROOT = REPO_ROOT / "modules" / "honcho"
HONCHO_COMPOSE = REPO_ROOT / "stack" / "docker-compose.honcho.yml"
HONCHO_ENV = REPO_ROOT / "stack" / "env" / "rendered" / "honcho.env"


def compose_files() -> list[Path]:
    """Return the compose files required for Honcho."""
    return [data_plane.LAI_COMPOSE, data_plane.OVERLAY_COMPOSE, HONCHO_COMPOSE]


def ensure_layout() -> None:
    """Validate required files for the Honcho phase."""
    data_plane.ensure_layout()
    missing = [str(path) for path in (HONCHO_ROOT / "Dockerfile", HONCHO_COMPOSE) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing Honcho inputs:\n- " + "\n- ".join(missing))


def render_env(root_env_path: Path) -> Path:
    """Render the downstream Honcho env file from the root env file."""
    ensure_layout()
    values = honcho.render_env(envfile.parse(root_env_path))
    honcho.write_env(HONCHO_ENV, values)
    return HONCHO_ENV


def bring_up(root_env_path: Path, *, timeout_s: float = 120.0) -> Path:
    """Bring up self-hosted Honcho after the Phase 1 data plane exists."""
    rendered_env = render_env(root_env_path)
    compose.run(
        data_plane.PROJECT,
        compose_files(),
        ["up", "-d", "honcho-api", "honcho-deriver"],
        cwd=REPO_ROOT,
        env=envfile.parse(root_env_path),
    )
    honcho.wait_for_honcho(timeout_s=timeout_s)
    return rendered_env
