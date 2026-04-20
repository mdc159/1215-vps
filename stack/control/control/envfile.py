"""Parse and render `.env` files.

Format rules:
- One KEY=VALUE per line.
- Lines starting with `#` (after optional whitespace) are comments.
- Blank lines are ignored.
- `=` inside the value is preserved.
- Surrounding single or double quotes are stripped from values.
- Keys must be [A-Za-z_][A-Za-z0-9_]*.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote as _quote

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse(path: Path) -> dict[str, str]:
    """Return a dict of key -> value from a `.env` file."""
    if not path.exists():
        return {}

    out: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}: line {lineno}: missing '=': {raw!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"{path}: line {lineno}: invalid key {key!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def render(template_path: Path, values: dict[str, str]) -> str:
    """Render a `.env` file using `template_path` for structure and `values` for data."""
    if not template_path.exists():
        raise FileNotFoundError(template_path)

    seen_keys: set[str] = set()
    out_lines: list[str] = []
    for lineno, raw in enumerate(template_path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if "=" not in stripped:
            raise ValueError(f"{template_path}: line {lineno}: missing '=': {raw!r}")
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"{template_path}: line {lineno}: invalid key {key!r}")
        seen_keys.add(key)
        out_lines.append(f"{key}={values.get(key, '')}")

    for key, val in values.items():
        if key not in seen_keys:
            out_lines.append(f"{key}={val}")

    return "\n".join(out_lines) + "\n"


def compose_honcho_uri(password: str) -> str:
    """Build the Honcho DB connection URI from the honcho_app password."""
    if not password:
        raise ValueError("password required")
    encoded = _quote(password, safe="")
    return f"postgresql+psycopg://honcho_app:{encoded}@db:5432/honcho"
