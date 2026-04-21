from __future__ import annotations

import importlib.util
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "stack" / "prototype-local" / "scripts" / "init_env.py"


def load_init_env_module():
    spec = importlib.util.spec_from_file_location("prototype_init_env", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_render_env_preserves_existing_secret_values() -> None:
    module = load_init_env_module()
    example = "\n".join(
        [
            "POSTGRES_PASSWORD=replace-postgres",
            "LANGFUSE_SALT=replace-salt",
            "ENCRYPTION_KEY=replace-encryption",
            "NEXTAUTH_SECRET=replace-nextauth",
            "N8N_ENCRYPTION_KEY=replace-n8n",
            "HONCHO_DATABASE_NAME=honcho",
            "HONCHO_BASE_URL=http://127.0.0.1:18000",
            "N8N_API_KEY=replace-api",
            "OPENAI_API_KEY=",
            "",
        ]
    )
    existing = {
        "POSTGRES_PASSWORD": "kept-postgres",
        "LANGFUSE_SALT": "a" * 64,
        "ENCRYPTION_KEY": "b" * 64,
        "NEXTAUTH_SECRET": "kept-nextauth",
        "N8N_ENCRYPTION_KEY": "c" * 64,
        "HONCHO_DATABASE_NAME": "honcho",
        "HONCHO_BASE_URL": "http://127.0.0.1:18000",
        "N8N_API_KEY": "kept-api",
        "OPENAI_API_KEY": "kept-openai",
    }

    rendered = module.render_env(example, existing)

    assert "POSTGRES_PASSWORD=kept-postgres" in rendered
    assert f"LANGFUSE_SALT={'a' * 64}" in rendered
    assert f"ENCRYPTION_KEY={'b' * 64}" in rendered
    assert "NEXTAUTH_SECRET=kept-nextauth" in rendered
    assert f"N8N_ENCRYPTION_KEY={'c' * 64}" in rendered
    assert "HONCHO_DATABASE_NAME=honcho" in rendered
    assert "HONCHO_BASE_URL=http://127.0.0.1:18000" in rendered
    assert "N8N_API_KEY=kept-api" in rendered
    assert "OPENAI_API_KEY=kept-openai" in rendered


def test_render_env_regenerates_invalid_langfuse_encryption_key() -> None:
    module = load_init_env_module()
    example = "\n".join(
        [
            "ENCRYPTION_KEY=replace-encryption",
            "",
        ]
    )
    rendered = module.render_env(example, {"ENCRYPTION_KEY": "not-valid"})
    match = re.search(r"^ENCRYPTION_KEY=(.+)$", rendered, re.MULTILINE)
    assert match is not None
    value = match.group(1)
    assert re.fullmatch(r"[0-9a-f]{64}", value) is not None
    assert value != "not-valid"


def test_render_env_drops_retired_honcho_db_keys() -> None:
    """HONCHO_DB_PASSWORD / HONCHO_DB_CONNECTION_URI were retired when Honcho
    moved off its own pgvector container onto the shared substrate Postgres
    (Phase B). Keys no longer present in the template must not bleed through
    from an older local .env."""
    module = load_init_env_module()
    example = "\n".join(
        [
            "POSTGRES_PASSWORD=replace-postgres",
            "HONCHO_DATABASE_NAME=honcho",
            "",
        ]
    )
    existing = {
        "POSTGRES_PASSWORD": "kept-postgres",
        "HONCHO_DB_PASSWORD": "leftover",
        "HONCHO_DB_CONNECTION_URI": "postgresql+psycopg://honcho_app:leftover@postgres:5432/honcho",
    }
    rendered = module.render_env(example, existing)
    assert "HONCHO_DB_PASSWORD" not in rendered
    assert "HONCHO_DB_CONNECTION_URI" not in rendered
    assert "HONCHO_DATABASE_NAME=honcho" in rendered
