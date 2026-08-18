"""Configuration loader and validator."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
SECRETS_PATH = CONFIG_DIR / "secrets.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile() -> str:
    profile_path = CONFIG_DIR / "profile.md"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"config/profile.md not found. "
            f"Copy config/profile.example.md to config/profile.md and fill it in."
        )
    with open(profile_path, "r", encoding="utf-8") as f:
        return f.read()


def load_sources() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "sources.yaml")


def load_secrets() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        return {}
    return load_yaml(SECRETS_PATH) or {}


def save_secrets(updates: dict[str, Any]) -> dict[str, Any]:
    data = load_secrets()
    for key, val in updates.items():
        if val is None:
            continue
        if val == "" and key.endswith("_api_key"):
            continue
        data[key] = val
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SECRETS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return data


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 4:
        return "****"
    return "…" + key[-4:]


def settings_public() -> dict[str, Any]:
    gemini = get_gemini_key()
    deepseek = get_deepseek_key()
    pagespeed = get_pagespeed_key()
    return {
        "provider": get_llm_provider(),
        "has_key": bool(gemini or deepseek),
        "gemini_suffix": _mask_key(gemini),
        "deepseek_suffix": _mask_key(deepseek),
        "has_pagespeed_key": bool(pagespeed),
        "pagespeed_suffix": _mask_key(pagespeed),
    }


def load_scoring() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "scoring.yaml")


def get_deepseek_key() -> str | None:
    """Return DeepSeek API key from env, local secrets, or sources.yaml."""
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    secrets_key = load_secrets().get("deepseek_api_key")
    if secrets_key:
        return str(secrets_key)
    sources = load_sources()
    key = sources.get("apis", {}).get("deepseek", {}).get("api_key")
    return key if key else None


def get_gemini_key() -> str | None:
    """Return Gemini API key from env, local secrets, or sources.yaml."""
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key
    secrets_key = load_secrets().get("gemini_api_key")
    if secrets_key:
        return str(secrets_key)
    sources = load_sources()
    key = sources.get("apis", {}).get("gemini", {}).get("api_key")
    return key if key else None


def get_pagespeed_key() -> str | None:
    """Return PageSpeed Insights API key from env, local secrets, or sources.yaml.

    Google's PageSpeed API has a 0/day quota for anonymous callers, so this
    collector silently returns nulls without a key."""
    env_key = os.environ.get("PAGESPEED_API_KEY")
    if env_key:
        return env_key
    secrets_key = load_secrets().get("pagespeed_api_key")
    if secrets_key:
        return str(secrets_key)
    sources = load_sources()
    key = sources.get("apis", {}).get("pagespeed", {}).get("api_key")
    return key if key else None


def get_llm_provider() -> str:
    """Return preferred LLM provider (gemini or deepseek)."""
    secrets_provider = load_secrets().get("preferred_provider")
    sources = load_sources()
    provider = secrets_provider or sources.get("apis", {}).get("preferred_provider") or "gemini"
    if provider == "gemini" and not get_gemini_key():
        if get_deepseek_key():
            return "deepseek"
    elif provider == "deepseek" and not get_deepseek_key():
        if get_gemini_key():
            return "gemini"
    return provider


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)
