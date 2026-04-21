#!/usr/bin/env python3
"""Render a local prototype `.env` from the committed example."""

from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXAMPLE = REPO_ROOT / "stack" / "prototype-local" / ".env.example"
DEFAULT_OUTPUT = REPO_ROOT / "stack" / "prototype-local" / ".env"


def token_urlsafe(num_bytes: int = 24) -> str:
    return secrets.token_urlsafe(num_bytes)


def token_b64(num_bytes: int = 32) -> str:
    return base64.b64encode(secrets.token_bytes(num_bytes)).decode("ascii")


GENERATORS = {
    "POSTGRES_PASSWORD": lambda: token_urlsafe(),
    "MINIO_ROOT_PASSWORD": lambda: token_urlsafe(),
    "CLICKHOUSE_PASSWORD": lambda: token_urlsafe(),
    "LANGFUSE_SALT": lambda: secrets.token_hex(16),
    "ENCRYPTION_KEY": lambda: token_b64(),
    "NEXTAUTH_SECRET": lambda: token_b64(),
    "N8N_ENCRYPTION_KEY": lambda: token_b64(),
    "N8N_USER_MANAGEMENT_JWT_SECRET": lambda: token_b64(),
    "N8N_MCP_AUTH_TOKEN": lambda: token_b64(),
    "N8N_OWNER_PASSWORD": lambda: token_urlsafe(),
    "NEO4J_AUTH": lambda: f"neo4j/{token_urlsafe()}",
    "OPEN_WEBUI_ADMIN_PASSWORD": lambda: token_urlsafe(),
}

BLANK_KEYS = {
    "N8N_API_KEY",
    "OPENROUTER_API_KEY",
}


def render_env(example_text: str) -> str:
    rendered_lines: list[str] = []
    generated_values = {key: generator() for key, generator in GENERATORS.items()}

    for line in example_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered_lines.append(line)
            continue

        key, _ = line.split("=", 1)
        if key in generated_values:
            rendered_lines.append(f"{key}={generated_values[key]}")
        elif key in BLANK_KEYS:
            rendered_lines.append(f"{key}=")
        else:
            rendered_lines.append(line)

    return "\n".join(rendered_lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render stack/prototype-local/.env from the committed example.",
    )
    parser.add_argument(
        "--example",
        type=Path,
        default=DEFAULT_EXAMPLE,
        help="Path to the committed .env.example template.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the local .env file to create or overwrite.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    example_path = args.example.resolve()
    output_path = args.output.resolve()

    if not example_path.exists():
        raise SystemExit(f"missing example template: {example_path}")
    if output_path.exists() and not args.force:
        raise SystemExit(
            f"refusing to overwrite existing env file: {output_path} (use --force)"
        )

    rendered = render_env(example_path.read_text())
    output_path.write_text(rendered)
    os.chmod(output_path, 0o600)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
