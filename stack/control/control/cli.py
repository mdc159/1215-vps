"""Command-line entry point for 1215-VPS."""
from __future__ import annotations

import logging
from pathlib import Path

import click

from control import compose, envfile
from control.phases import data_plane, honcho as honcho_phase, preflight

PHASE1_REQUIRED: dict[str, tuple[str, int]] = {
    "POSTGRES_PASSWORD": ("hex", 32),
    "JWT_SECRET": ("hex", 32),
    "DASHBOARD_PASSWORD": ("alnum", 24),
    "POOLER_TENANT_ID": ("alnum", 16),
    "HONCHO_DB_PASSWORD": ("hex", 32),
    "BROKER_APP_PASSWORD": ("hex", 32),
    "CLICKHOUSE_PASSWORD": ("hex", 32),
    "MINIO_ROOT_PASSWORD": ("hex", 32),
    "LANGFUSE_SALT": ("hex", 32),
    "NEXTAUTH_SECRET": ("hex", 32),
    "ENCRYPTION_KEY": ("hex", 32),
    "N8N_ENCRYPTION_KEY": ("hex", 32),
    "N8N_USER_MANAGEMENT_JWT_SECRET": ("hex", 32),
    "SEARXNG_SECRET_KEY": ("hex", 32),
    "FLOWISE_PASSWORD": ("alnum", 24),
}

PHASE1_COMPOSED: dict[str, str] = {
    "HONCHO_DB_CONNECTION_URI": "honcho_uri",
    "NEO4J_AUTH": "neo4j_auth",
}


def _require_example(env_dir: Path) -> tuple[Path, Path]:
    example = env_dir / ".env.example"
    env = env_dir / ".env"
    if not example.exists():
        raise click.ClickException(f"{example} not found")
    return env, example


def _ensure_env(env_dir: Path) -> Path:
    env, example = _require_example(env_dir)
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required=PHASE1_REQUIRED,
        composed=PHASE1_COMPOSED,
    )
    return env


def _compose_env(env_dir: Path) -> dict[str, str]:
    env, _ = _require_example(env_dir)
    if not env.exists():
        return {}
    return envfile.parse(env)


@click.group()
@click.option(
    "--env-dir",
    type=click.Path(path_type=Path),
    default=Path("stack/env"),
    help="Directory containing .env and .env.example.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
@click.pass_context
def main(ctx: click.Context, env_dir: Path, verbose: bool) -> None:
    """1215-VPS control plane."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["env_dir"] = env_dir


@main.command()
@click.option(
    "--no-generate",
    is_flag=True,
    help="Fail if secrets are missing instead of generating them.",
)
@click.pass_context
def check(ctx: click.Context, no_generate: bool) -> None:
    """Validate the environment file."""
    env_dir: Path = ctx.obj["env_dir"]
    env, _ = _require_example(env_dir)

    if no_generate:
        current = envfile.parse(env) if env.exists() else {}
        required_keys = set(PHASE1_REQUIRED) | set(PHASE1_COMPOSED)
        missing = sorted(key for key in required_keys if not current.get(key))
        if missing:
            raise click.ClickException(
                "missing or empty required keys: " + ", ".join(missing)
            )
        click.echo("check: all required keys present.")
        return

    values = preflight.ensure_env(
        env_path=env,
        example_path=env_dir / ".env.example",
        required=PHASE1_REQUIRED,
        composed=PHASE1_COMPOSED,
    )
    click.echo(f"check: OK - {len(values)} keys present in {env}.")


@main.command()
@click.option(
    "--first-boot/--not-first-boot",
    default=False,
    help="Use a longer timeout budget for first-time Supabase startup.",
)
@click.option(
    "--ollama-profile",
    default="none",
    type=click.Choice(["none", "cpu", "gpu-nvidia", "gpu-amd"]),
)
@click.option(
    "--with-honcho",
    is_flag=True,
    help="After Phase 1, bring up self-hosted Honcho (Plan 2).",
)
@click.pass_context
def up(
    ctx: click.Context,
    first_boot: bool,
    ollama_profile: str,
    with_honcho: bool,
) -> None:
    """Run preflight and bring up Phase 1."""
    env_dir: Path = ctx.obj["env_dir"]
    env_path = _ensure_env(env_dir)
    click.echo("=== Phase 1: data plane ===")
    data_plane.bring_up(
        env_path=env_path,
        first_boot=first_boot,
        ollama_profile=ollama_profile,
    )
    click.echo("phase 1 complete.")
    if with_honcho:
        click.echo("=== Phase 2: honcho ===")
        rendered = honcho_phase.bring_up(env_path)
        click.echo(f"phase 2 complete. rendered env: {rendered}")


@main.command()
@click.pass_context
def down(ctx: click.Context) -> None:
    """Tear down the Phase 1 stack."""
    env_dir: Path = ctx.obj["env_dir"]
    _require_example(env_dir)
    data_plane.ensure_layout()
    compose.run(
        data_plane.PROJECT,
        data_plane.compose_files(),
        ["down"],
        cwd=data_plane.REPO_ROOT,
        env=_compose_env(env_dir),
    )


@main.command()
@click.pass_context
def ps(ctx: click.Context) -> None:
    """Show compose service status."""
    env_dir: Path = ctx.obj["env_dir"]
    _require_example(env_dir)
    data_plane.ensure_layout()
    compose.run(
        data_plane.PROJECT,
        data_plane.compose_files(),
        ["ps"],
        cwd=data_plane.REPO_ROOT,
        env=_compose_env(env_dir),
    )


@main.command(context_settings={"ignore_unknown_options": True})
@click.argument("services", nargs=-1)
@click.pass_context
def logs(ctx: click.Context, services: tuple[str, ...]) -> None:
    """Stream compose logs for one or more services."""
    env_dir: Path = ctx.obj["env_dir"]
    _require_example(env_dir)
    data_plane.ensure_layout()
    compose.run(
        data_plane.PROJECT,
        data_plane.compose_files(),
        ["logs", *services],
        cwd=data_plane.REPO_ROOT,
        env=_compose_env(env_dir),
        check=False,
    )


@main.command(name="render-env")
@click.pass_context
def render_env(ctx: click.Context) -> None:
    """Render stack/env/.env from the template and print it."""
    env_dir: Path = ctx.obj["env_dir"]
    env_path = _ensure_env(env_dir)
    click.echo(env_path.read_text(), nl=False)
