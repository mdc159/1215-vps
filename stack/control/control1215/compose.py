from __future__ import annotations

from pathlib import Path

from .topology import load_targets, resolve_paths


def target_compose_files(target_name: str) -> list[Path]:
    targets = load_targets()["targets"]
    if target_name not in targets:
        raise KeyError(target_name)

    paths = resolve_paths()
    compose_files = targets[target_name].get("compose_files", [])
    return [paths.repo_root / relative_path for relative_path in compose_files]


def target_env_file(target_name: str) -> Path | None:
    targets = load_targets()["targets"]
    if target_name not in targets:
        raise KeyError(target_name)

    env_file = targets[target_name].get("env_file")
    if not env_file:
        return None

    paths = resolve_paths()
    return paths.repo_root / env_file


def docker_compose_args(
    target_name: str,
    *extra_args: str,
    profiles: list[str] | None = None,
) -> list[str]:
    command = ["docker", "compose"]
    env_file = target_env_file(target_name)
    if env_file is not None:
        command.extend(["--env-file", str(env_file)])
    for compose_file in target_compose_files(target_name):
        command.extend(["-f", str(compose_file)])
    for profile in profiles or []:
        command.extend(["--profile", profile])
    command.extend(extra_args)
    return command
