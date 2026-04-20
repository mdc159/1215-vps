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
