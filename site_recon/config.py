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
DEMO_ROOT = PROJECT_ROOT / "demo_data"
DEMO_LIMITS_PATH = CONFIG_DIR / "demo_limits.yaml"
DEMO_SECRETS_PATH = CONFIG_DIR / "demo_secrets.yaml"
SECRETS_PATH = CONFIG_DIR / "secrets.yaml"
REPO_URL = "https://github.com/esfanda/site-recon"


def is_public_demo() -> bool:
    return os.environ.get("SITE_RECON_PUBLIC_DEMO") == "1"


def data_dir() -> Path:
    if is_public_demo():
        return DEMO_ROOT / "data"
    return DATA_DIR


def reports_dir() -> Path:
    if is_public_demo():
        return DEMO_ROOT / "reports"
    return REPORTS_DIR


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile() -> str:
    if is_public_demo():
        raise RuntimeError("profile.md is not used in public demo mode")
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
    if is_public_demo():
        return {}
    if not SECRETS_PATH.exists():
        return {}
    return load_yaml(SECRETS_PATH) or {}


def save_secrets(updates: dict[str, Any]) -> dict[str, Any]:
    if is_public_demo():
        raise RuntimeError("Cannot save secrets in public demo mode")
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
    if is_public_demo():
        return {
            "public_demo": True,
            "provider": "gemini",
            "has_key": bool(get_demo_gemini_key()),
            "has_pagespeed_key": bool(get_pagespeed_key()),
        }
    gemini = get_gemini_key()
    deepseek = get_deepseek_key()
    pagespeed = get_pagespeed_key()
    return {
        "public_demo": False,
        "provider": get_llm_provider(),
        "has_key": bool(gemini or deepseek),
        "gemini_suffix": _mask_key(gemini),
        "deepseek_suffix": _mask_key(deepseek),
        "has_pagespeed_key": bool(pagespeed),
        "pagespeed_suffix": _mask_key(pagespeed),
    }


def load_scoring() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "scoring.yaml")


def get_demo_gemini_key() -> str | None:
    env_key = os.environ.get("SITE_RECON_DEMO_KEY")
    if env_key:
        return env_key.strip() or None
    if DEMO_SECRETS_PATH.exists():
        key = load_yaml(DEMO_SECRETS_PATH).get("gemini_api_key")
        if key and str(key) != "replace-me":
            return str(key)
    return None


def get_deepseek_key() -> str | None:
    if is_public_demo():
        return None
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
    if is_public_demo():
        return get_demo_gemini_key()
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
    if is_public_demo():
        env_key = os.environ.get("SITE_RECON_DEMO_PAGESPEED_KEY")
        if env_key:
            return env_key
        return None
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
    if is_public_demo():
        return "gemini"
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
    data_dir().mkdir(parents=True, exist_ok=True)
    reports_dir().mkdir(parents=True, exist_ok=True)
    (data_dir() / "cache").mkdir(parents=True, exist_ok=True)
