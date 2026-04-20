"""Tests for Honcho env rendering."""
from __future__ import annotations

import pytest

from control import honcho


def test_render_env_maps_openai_compatible_provider():
    rendered = honcho.render_env(
        {
            "HONCHO_DB_CONNECTION_URI": "postgresql+psycopg://honcho_app:pw@db:5432/honcho",
            "HONCHO_CACHE_URL": "redis://redis:6379/1?suppress=true",
            "HONCHO_CACHE_ENABLED": "true",
            "HONCHO_LLM_PROVIDER": "openai-compatible",
            "HONCHO_LLM_API_KEY": "key-123",
            "HONCHO_LLM_BASE_URL": "http://ollama:11434/v1",
            "HONCHO_LLM_MODEL": "llama3.1",
        }
    )
    assert rendered["DB_CONNECTION_URI"].startswith("postgresql+psycopg://")
    assert rendered["CACHE_URL"] == "redis://redis:6379/1?suppress=true"
    assert rendered["DERIVER_PROVIDER"] == "custom"
    assert rendered["LLM_OPENAI_COMPATIBLE_API_KEY"] == "key-123"
    assert rendered["LLM_OPENAI_COMPATIBLE_BASE_URL"] == "http://ollama:11434/v1"
    assert rendered["LLM_EMBEDDING_PROVIDER"] == "openrouter"


def test_render_env_disables_embeddings_without_supported_fallback():
    rendered = honcho.render_env(
        {
            "HONCHO_DB_CONNECTION_URI": "postgresql+psycopg://honcho_app:pw@db:5432/honcho",
            "HONCHO_CACHE_URL": "redis://redis:6379/1?suppress=true",
            "HONCHO_CACHE_ENABLED": "true",
            "HONCHO_LLM_PROVIDER": "anthropic",
            "HONCHO_LLM_API_KEY": "key-123",
            "HONCHO_LLM_MODEL": "claude-sonnet-4-20250514",
        }
    )
    assert rendered["DERIVER_PROVIDER"] == "anthropic"
    assert rendered["LLM_ANTHROPIC_API_KEY"] == "key-123"
    assert rendered["EMBED_MESSAGES"] == "false"


def test_render_env_rejects_missing_provider_inputs():
    with pytest.raises(ValueError, match="HONCHO_LLM_API_KEY"):
        honcho.render_env(
            {
                "HONCHO_DB_CONNECTION_URI": "postgresql+psycopg://honcho_app:pw@db:5432/honcho",
                "HONCHO_LLM_PROVIDER": "openai",
                "HONCHO_LLM_MODEL": "gpt-4.1-mini",
            }
        )
