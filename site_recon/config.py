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


def load_scoring() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "scoring.yaml")


def get_deepseek_key() -> str | None:
    """Return DeepSeek API key from env or config."""
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    sources = load_sources()
    key = sources.get("apis", {}).get("deepseek", {}).get("api_key")
    return key if key else None


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "cache").mkdir(parents=True, exist_ok=True)
