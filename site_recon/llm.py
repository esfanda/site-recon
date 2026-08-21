"""DeepSeek LLM client with caching, schema validation, retries."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from site_recon.config import get_deepseek_key, get_gemini_key, get_llm_provider
from site_recon.utils import cache_read, cache_write


class RateLimitError(RuntimeError):
    """Provider returned HTTP 429."""


def probe_key(provider: str, api_key: str) -> tuple[bool, str]:
    """Hit the provider with a tiny request. Return (ok, error_for_humans). Do not echo the key."""
    key = (api_key or "").strip()
    if not key:
        return False, "No API key"
    try:
        if provider == "deepseek":
            resp = httpx.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15.0,
            )
        else:
            resp = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=15.0,
            )
    except httpx.TimeoutException:
        return False, "Provider timed out. Try again."
    except httpx.RequestError:
        return False, "Could not reach the provider."
    if resp.status_code in (400, 401, 403):
        return False, "This key was rejected. Paste a new key from the link above."
    if resp.status_code != 200:
        return False, f"Provider returned HTTP {resp.status_code}."
    if provider != "deepseek":
        return True, ""
    # Listing models is free. Chat is not. A zero-balance key passes /models and fails Analyze.
    try:
        chat = httpx.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "Reply with JSON: {\"ok\":true}"}],
                "max_tokens": 8,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=20.0,
        )
    except httpx.TimeoutException:
        return False, "Provider timed out. Try again."
    except httpx.RequestError:
        return False, "Could not reach the provider."
    if chat.status_code == 200:
        return True, ""
    if chat.status_code == 402:
        return False, "This DeepSeek key is valid, but the account has no credit. Add credit, then Save again."
    if chat.status_code in (400, 401, 403):
        return False, "This key was rejected. Paste a new key from the link above."
    return False, f"Provider returned HTTP {chat.status_code}."


def _unwrap_schema_envelope(data: Any) -> Any:
    """Return the payload when the model echoes the JSON Schema around it.

    Gemini sometimes answers with `{"type": "object", "properties": {...}}`,
    the schema it was handed, with the real content sitting inside
    `properties`. Callers then read every section as missing and the whole
    report renders blank, which is worse than an error because nothing says
    anything went wrong.
    """
    if not isinstance(data, dict):
        return data
    if data.get("type") == "object" and isinstance(data.get("properties"), dict):
        return data["properties"]
    return data


def call_llm(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any] | None = None,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    retries: int = 2,
    image_path: str | Path | None = None,
) -> dict[str, Any]:
    provider = get_llm_provider()

    if provider == "gemini":
        return _unwrap_schema_envelope(
            _call_gemini(system_prompt, user_prompt, schema, max_tokens, temperature, retries, image_path)
        )
    else:
        # DeepSeek's chat model is text-only. There is no vision fallback here:
        # silently dropping the image would let the model keep guessing about
        # layout it never saw, so the caller must make sure the prompt tells it
        # to skip visual claims outright when this branch runs.
        return _unwrap_schema_envelope(
            _call_deepseek(system_prompt, user_prompt, schema, max_tokens, temperature, retries)
        )


def _call_deepseek(
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

    cache_key = hashlib.sha256(("deepseek" + system_prompt + user_prompt + json.dumps(schema or {})).encode()).hexdigest()[:32]
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
            if resp.status_code == 429:
                if attempt < retries:
                    time.sleep(20)
                    continue
                raise RateLimitError("rate_limit")
            if resp.status_code == 402:
                raise RuntimeError("no_credit")
            if resp.status_code in (401, 403):
                raise RuntimeError("bad_key")
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            cache_write(f"llm:{cache_key}", {"value": parsed, "cached_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
            return parsed
        except RateLimitError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError("LLM call failed") from exc
    raise RuntimeError("unreachable")


def _gemini_text(data: dict[str, Any]) -> str:
    err = data.get("error")
    if err:
        code = err.get("code") if isinstance(err, dict) else None
        raise RuntimeError("unavailable" if code == 503 else "Gemini API error")
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError("unavailable")
    parts = (cands[0].get("content") or {}).get("parts") or []
    texts: list[str] = []
    for part in parts:
        if part.get("thought"):
            continue
        text = part.get("text")
        if text:
            texts.append(text)
    if not texts:
        reason = cands[0].get("finishReason") or "empty"
        raise RuntimeError(f"Gemini empty ({reason})")
    blob = "\n".join(texts).strip()
    if blob.startswith("```"):
        blob = blob.strip("`")
        if blob.lower().startswith("json"):
            blob = blob[4:]
        blob = blob.strip()
    return blob
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError("unavailable")
    parts = (cands[0].get("content") or {}).get("parts") or []
    texts: list[str] = []
    for part in parts:
        if part.get("thought"):
            continue
        text = part.get("text")
        if text:
            texts.append(text)
    if not texts:
        reason = cands[0].get("finishReason") or "empty"
        raise RuntimeError(f"Gemini empty ({reason})")
    return "\n".join(texts)


def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any] | None = None,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    retries: int = 2,
    image_path: str | Path | None = None,
) -> dict[str, Any]:
    api_key = get_gemini_key()
    if not api_key:
        raise RuntimeError("Gemini API key not configured. Set GEMINI_API_KEY or config/sources.yaml apis.gemini.api_key")

    image_b64 = None
    if image_path:
        try:
            image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        except OSError:
            image_b64 = None

    cache_key = hashlib.sha256(
        ("gemini" + system_prompt + user_prompt + json.dumps(schema or {}) + (image_b64 or "")).encode()
    ).hexdigest()[:32]
    cached = cache_read(f"llm:{cache_key}", ttl_hours=168)
    if cached is not None:
        return cached.get("value", cached)

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    if schema:
        full_prompt += (
            "\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            "Do not include markdown code fences. Only raw JSON."
        )

    parts: list[dict[str, object]] = [{"text": full_prompt}]
    if image_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": image_b64}})

    payload = {
        "contents": [
            {"role": "user", "parts": parts}
        ],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "responseMimeType": "application/json" if schema else "text/plain",
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }

    # flash-latest (3.7) free tier is 20 requests/day. Lite has a separate quota.
    model = "gemini-flash-lite-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json=payload,
                timeout=120.0,
            )
            if resp.status_code == 429:
                if "PerDay" in (resp.text or ""):
                    raise RateLimitError("rate_limit")
                if attempt < retries:
                    time.sleep(20)
                    continue
                raise RateLimitError("rate_limit")
            if resp.status_code == 503:
                if attempt < retries:
                    time.sleep(20)
                    continue
                raise RuntimeError("unavailable")
            if resp.status_code in (401, 403):
                raise RuntimeError("bad_key")
            resp.raise_for_status()
            data = resp.json()
            parsed = json.loads(_gemini_text(data))
            cache_write(
                f"llm:{cache_key}",
                {
                    "value": parsed,
                    "cached_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                },
            )
            return parsed
        except RateLimitError:
            raise
        except RuntimeError:
            raise
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (400, 401, 403):
                raise RuntimeError("bad_key") from None
            if attempt == retries:
                raise RuntimeError(f"Gemini HTTP {code}") from None
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError("Gemini call failed") from exc
    raise RuntimeError("Gemini call failed")
