from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .topology import load_roles, resolve_paths


@dataclass(frozen=True)
class NodeManifest:
    name: str
    target: str
    roles: tuple[str, ...]
    manifest_path: Path
    used_example: bool


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"invalid env line in {path}: {raw_line!r}")
        values[key.strip()] = value.strip()
    return values


def _node_manifest_path(node_name: str) -> tuple[Path, bool]:
    paths = resolve_paths()
    node_dir = paths.nodes_root / node_name
    manifest = node_dir / "roles.env"
    if manifest.exists():
        return manifest, False
    example = node_dir / "roles.env.example"
    if example.exists():
        return example, True
    raise KeyError(node_name)


def list_node_names() -> list[str]:
    paths = resolve_paths()
    names: list[str] = []
    for child in sorted(paths.nodes_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "roles.env").exists() or (child / "roles.env.example").exists():
            names.append(child.name)
    return names


def load_node_manifest(node_name: str) -> NodeManifest:
    manifest_path, used_example = _node_manifest_path(node_name)
    values = _parse_env_file(manifest_path)

    target = values.get("TARGET", "prototype-local")
    raw_roles = values.get("ENABLED_ROLES", "")
    roles = tuple(role.strip() for role in raw_roles.split(",") if role.strip())

    if not roles:
        raise ValueError(f"node '{node_name}' has no ENABLED_ROLES in {manifest_path}")

    return NodeManifest(
        name=values.get("NODE_NAME", node_name),
        target=target,
        roles=roles,
        manifest_path=manifest_path,
        used_example=used_example,
    )


def role_compose_profiles(role_names: tuple[str, ...]) -> list[str]:
    roles = load_roles()["roles"]
    selected_profiles: list[str] = []
    for role_name in role_names:
        if role_name not in roles:
            raise KeyError(role_name)
        for profile in roles[role_name].get("compose_profiles", []):
            if profile not in selected_profiles:
                selected_profiles.append(profile)
    return selected_profiles
