"""Phase 0 — preflight."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from control import envfile, secrets


_COMPOSERS = {
    "honcho_uri": lambda values: envfile.compose_honcho_uri(
        password=values["HONCHO_DB_PASSWORD"]
    ),
    "neo4j_auth": lambda values: f"neo4j/{secrets.generate_hex(32)}",
}


def ensure_env(
    env_path: Path,
    example_path: Path,
    required: Mapping[str, tuple[str, int]],
    composed: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Guarantee `env_path` exists with every required secret populated."""
    current = (
        envfile.parse(env_path)
        if env_path.exists()
        else envfile.parse(example_path)
    )
    populated = secrets.populate_missing(current, dict(required))

    for key, composer_name in (composed or {}).items():
        composer = _COMPOSERS.get(composer_name)
        if composer is None:
            raise ValueError(f"unknown composer {composer_name!r} for {key}")
        if not populated.get(key):
            populated[key] = composer(populated)

    env_path.write_text(envfile.render(example_path, populated))
    return populated
