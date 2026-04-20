"""Tests for preflight phase: .env validation + auto-generation."""
from pathlib import Path

from control.phases import preflight


def test_ensure_env_creates_env_from_example_if_absent(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("FOO=\nBAR=static\n")
    env = tmp_path / ".env"
    preflight.ensure_env(env_path=env, example_path=example, required={})
    assert env.exists()
    content = env.read_text()
    assert "FOO=\n" in content
    assert "BAR=static\n" in content


def test_ensure_env_generates_missing_required_secrets(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("SECRET=\nKEEP=static\n")
    env = tmp_path / ".env"
    env.write_text("SECRET=\nKEEP=static\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    content = env.read_text()
    import re

    match = re.search(r"^SECRET=([0-9a-f]{64})$", content, re.MULTILINE)
    assert match, f"SECRET not generated: {content!r}"
    assert "KEEP=static\n" in content


def test_ensure_env_composes_honcho_uri_when_password_present(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("HONCHO_DB_PASSWORD=\nHONCHO_DB_CONNECTION_URI=\n")
    env = tmp_path / ".env"
    env.write_text("HONCHO_DB_PASSWORD=\nHONCHO_DB_CONNECTION_URI=\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"HONCHO_DB_PASSWORD": ("hex", 32)},
        composed={"HONCHO_DB_CONNECTION_URI": "honcho_uri"},
    )
    content = env.read_text()
    assert "HONCHO_DB_CONNECTION_URI=postgresql+psycopg://honcho_app:" in content
    assert "@db:5432/honcho" in content


def test_ensure_env_is_idempotent(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("SECRET=\n")
    env = tmp_path / ".env"
    env.write_text("SECRET=\n")
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    first = env.read_text()
    preflight.ensure_env(
        env_path=env,
        example_path=example,
        required={"SECRET": ("hex", 32)},
    )
    second = env.read_text()
    assert first == second, "idempotent call changed the file"
