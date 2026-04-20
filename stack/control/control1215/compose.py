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


def docker_compose_args(target_name: str, *extra_args: str) -> list[str]:
    command = ["docker", "compose"]
    for compose_file in target_compose_files(target_name):
        command.extend(["-f", str(compose_file)])
    command.extend(extra_args)
    return command
