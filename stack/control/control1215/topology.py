from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    stack_root: Path
    topology_root: Path
    docs_root: Path
    modules_root: Path


def resolve_paths() -> Paths:
    repo_root = Path(__file__).resolve().parents[3]
    stack_root = repo_root / "stack"
    return Paths(
        repo_root=repo_root,
        stack_root=stack_root,
        topology_root=stack_root / "topology",
        docs_root=repo_root / "docs" / "architecture",
        modules_root=repo_root / "modules",
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_targets() -> dict:
    paths = resolve_paths()
    return load_json(paths.topology_root / "targets.json")


def load_services() -> dict:
    paths = resolve_paths()
    return load_json(paths.topology_root / "services.json")


def list_architecture_docs() -> list[Path]:
    paths = resolve_paths()
    return sorted(paths.docs_root.glob("*.md"))

