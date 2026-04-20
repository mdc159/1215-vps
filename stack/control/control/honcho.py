"""Honcho env rendering and readiness helpers."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Mapping

import requests

SUPPORTED_PROVIDERS = {
    "openai-compatible": "custom",
    "custom": "custom",
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "gemini": "google",
    "groq": "groq",
}

_DIALECTIC_LEVELS = ("minimal", "low", "medium", "high", "max")


def _require(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is required for Honcho self-hosting")
    return value


def _provider_env(prefix: str, provider: str, api_key: str, base_url: str | None) -> dict[str, str]:
    normalized = SUPPORTED_PROVIDERS.get(provider.strip().lower())
    if normalized is None:
        raise ValueError(f"unsupported HONCHO provider {provider!r}")

    out = {prefix: normalized}
    if normalized == "custom":
        out["LLM_OPENAI_COMPATIBLE_API_KEY"] = api_key
        out["LLM_OPENAI_COMPATIBLE_BASE_URL"] = _require(
            {"HONCHO_LLM_BASE_URL": base_url or ""},
            "HONCHO_LLM_BASE_URL",
        )
    elif normalized == "openai":
        out["LLM_OPENAI_API_KEY"] = api_key
    elif normalized == "anthropic":
        out["LLM_ANTHROPIC_API_KEY"] = api_key
    elif normalized == "google":
        out["LLM_GEMINI_API_KEY"] = api_key
    elif normalized == "groq":
        out["LLM_GROQ_API_KEY"] = api_key
    return out


def render_env(values: Mapping[str, str]) -> dict[str, str]:
    """Translate root semantic Honcho env keys into upstream Honcho env keys."""
    provider = _require(values, "HONCHO_LLM_PROVIDER")
    api_key = _require(values, "HONCHO_LLM_API_KEY")
    model = _require(values, "HONCHO_LLM_MODEL")
    base_url = values.get("HONCHO_LLM_BASE_URL", "").strip() or None

    out: dict[str, str] = {
        "DB_CONNECTION_URI": _require(values, "HONCHO_DB_CONNECTION_URI"),
        "CACHE_URL": values.get("HONCHO_CACHE_URL", "redis://redis:6379/1?suppress=true"),
        "CACHE_ENABLED": values.get("HONCHO_CACHE_ENABLED", "true"),
        "AUTH_USE_AUTH": "false",
        "VECTOR_STORE_TYPE": "pgvector",
    }
    out.update(_provider_env("DERIVER_PROVIDER", provider, api_key, base_url))
    out["DERIVER_MODEL"] = model
    out["SUMMARY_PROVIDER"] = out["DERIVER_PROVIDER"]
    out["SUMMARY_MODEL"] = model
    out["DREAM_PROVIDER"] = out["DERIVER_PROVIDER"]
    out["DREAM_MODEL"] = model
    out["DREAM_DEDUCTION_MODEL"] = model
    out["DREAM_INDUCTION_MODEL"] = model
    for level in _DIALECTIC_LEVELS:
        out[f"DIALECTIC_LEVELS__{level}__PROVIDER"] = out["DERIVER_PROVIDER"]
        out[f"DIALECTIC_LEVELS__{level}__MODEL"] = model

    embedding_provider = values.get("HONCHO_EMBEDDING_PROVIDER", "").strip()
    embedding_key = values.get("HONCHO_EMBEDDING_API_KEY", "").strip()
    embedding_base = values.get("HONCHO_EMBEDDING_BASE_URL", "").strip() or None

    if embedding_provider:
        mapped = embedding_provider.replace("openai-compatible", "openrouter")
        if mapped == "google":
            mapped = "gemini"
        if mapped not in {"openai", "gemini", "openrouter"}:
            raise ValueError(f"unsupported HONCHO_EMBEDDING_PROVIDER {embedding_provider!r}")
        out["LLM_EMBEDDING_PROVIDER"] = mapped
        if not embedding_key:
            raise ValueError("HONCHO_EMBEDDING_API_KEY is required when embedding provider is set")
        if mapped == "openai":
            out["LLM_OPENAI_API_KEY"] = embedding_key
        elif mapped == "gemini":
            out["LLM_GEMINI_API_KEY"] = embedding_key
        else:
            out["LLM_OPENAI_COMPATIBLE_API_KEY"] = embedding_key
            if embedding_base:
                out["LLM_OPENAI_COMPATIBLE_BASE_URL"] = embedding_base
    elif out["DERIVER_PROVIDER"] == "custom":
        out["LLM_EMBEDDING_PROVIDER"] = "openrouter"
    elif out["DERIVER_PROVIDER"] == "openai":
        out["LLM_EMBEDDING_PROVIDER"] = "openai"
    elif out["DERIVER_PROVIDER"] == "google":
        out["LLM_EMBEDDING_PROVIDER"] = "gemini"
    else:
        out["EMBED_MESSAGES"] = "false"

    return out


def write_env(path: Path, values: Mapping[str, str]) -> None:
    """Write a deterministic env file for Honcho containers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    path.write_text("\n".join(lines) + "\n")


def wait_for_honcho(base_url: str = "http://127.0.0.1:8000", timeout_s: float = 120.0) -> None:
    """Wait for the Honcho API health endpoint to return success."""
    deadline = time.monotonic() + timeout_s
    url = f"{base_url.rstrip('/')}/health"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=5)
        except requests.RequestException:
            time.sleep(2)
            continue
        if response.ok:
            return
        time.sleep(2)
    raise TimeoutError(f"Honcho API health check timed out for {url}")
