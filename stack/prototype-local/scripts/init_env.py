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


def token_hex(num_bytes: int = 32) -> str:
    return secrets.token_hex(num_bytes)


GENERATORS = {
    "POSTGRES_PASSWORD": lambda: token_urlsafe(),
    "MINIO_ROOT_PASSWORD": lambda: token_urlsafe(),
    "CLICKHOUSE_PASSWORD": lambda: token_urlsafe(),
    "LANGFUSE_SALT": lambda: token_hex(),
    "ENCRYPTION_KEY": lambda: token_hex(),
    "NEXTAUTH_SECRET": lambda: token_b64(),
    "N8N_ENCRYPTION_KEY": lambda: token_b64(),
    "N8N_USER_MANAGEMENT_JWT_SECRET": lambda: token_b64(),
    "N8N_MCP_AUTH_TOKEN": lambda: token_b64(),
    "N8N_OWNER_PASSWORD": lambda: token_urlsafe(),
    "NEO4J_AUTH": lambda: f"neo4j/{token_urlsafe()}",
    "OPEN_WEBUI_ADMIN_PASSWORD": lambda: token_urlsafe(),
    "HONCHO_DB_PASSWORD": lambda: token_hex(),
    "BROKER_APP_PASSWORD": lambda: token_hex(),
    "BETTER_AUTH_SECRET": lambda: token_urlsafe(),
}

BLANK_KEYS = {
    "N8N_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "HONCHO_LLM_API_KEY",
    "HONCHO_EMBEDDING_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
}


def parse_env_assignments(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def should_preserve_value(key: str, value: str, placeholders: dict[str, str]) -> bool:
    if not value:
        return False
    if value == placeholders.get(key):
        return False
    if key == "ENCRYPTION_KEY":
        return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())
    return True


def render_honcho_db_connection_uri(password: str) -> str:
    return f"postgresql+psycopg://honcho_app:{password}@postgres:5432/honcho"


def render_env(example_text: str, existing_values: dict[str, str] | None = None) -> str:
    rendered_values: dict[str, str] = {}
    generated_values = {key: generator() for key, generator in GENERATORS.items()}
    placeholders = parse_env_assignments(example_text)
    existing_values = existing_values or {}

    for line in example_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue

        key, _ = line.split("=", 1)
        if key in generated_values:
            existing_value = existing_values.get(key, "")
            if should_preserve_value(key, existing_value, placeholders):
                rendered_values[key] = existing_value
            else:
                rendered_values[key] = generated_values[key]
        elif key in BLANK_KEYS:
            existing_value = existing_values.get(key, "")
            rendered_values[key] = existing_value
        else:
            existing_value = existing_values.get(key, "")
            if existing_value and existing_value != placeholders.get(key):
                rendered_values[key] = existing_value
            else:
                rendered_values[key] = placeholders[key]

    if "HONCHO_DB_CONNECTION_URI" in placeholders and "HONCHO_DB_PASSWORD" in rendered_values:
        rendered_values["HONCHO_DB_CONNECTION_URI"] = render_honcho_db_connection_uri(
            rendered_values["HONCHO_DB_PASSWORD"]
        )

    rendered_lines: list[str] = []
    for line in example_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        rendered_lines.append(f"{key}={rendered_values[key]}")

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

    example_text = example_path.read_text()
    existing_values = parse_env_assignments(output_path.read_text()) if output_path.exists() else {}
    rendered = render_env(example_text, existing_values)
    output_path.write_text(rendered)
    os.chmod(output_path, 0o600)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
