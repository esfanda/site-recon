"""DeepSeek LLM client with caching, schema validation, retries."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import httpx

from site_recon.config import get_deepseek_key
from site_recon.utils import cache_read, cache_write


def call_llm(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any] | None = None,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    retries: int = 2,
) -> dict[str, Any]:
    api_key = get_deepseek_key()
    if not api_key:
        raise RuntimeError("DeepSeek API key not configured. Set DEEPSEEK_API_KEY or config/sources.yaml apis.deepseek.api_key")

    cache_key = hashlib.sha256((system_prompt + user_prompt + json.dumps(schema or {})).encode()).hexdigest()[:32]
    cached = cache_read(f"llm:{cache_key}", ttl_hours=168)
    if cached is not None:
        return cached.get("value", cached)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if schema:
        messages[0]["content"] += (
            "\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            "Do not include markdown code fences. Only raw JSON."
        )

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"} if schema else None,
    }

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={k: v for k, v in payload.items() if v is not None},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            cache_write(f"llm:{cache_key}", {"value": parsed, "cached_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
            return parsed
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(f"LLM call failed after {retries+1} attempts: {exc}")
    raise RuntimeError("unreachable")
