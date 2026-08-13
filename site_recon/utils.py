"""Shared utilities: caching, rate limiting, HTTP helpers."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from site_recon.config import DATA_DIR

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "SiteReconBot/1.0 (research tool; respects robots.txt)"


class RateLimiter:
    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.last_request: dict[str, float] = {}

    def wait(self, host: str) -> None:
        now = time.time()
        last = self.last_request.get(host, 0)
        elapsed = now - last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request[host] = time.time()


rate_limiter = RateLimiter(delay=1.0)


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
    timeout: float = 30.0,
    retries: int = 3,
) -> httpx.Response:
    """Rate-limited HTTP GET with retries."""
    host = httpx.URL(url).host
    rate_limiter.wait(host)

    default_headers = {"User-Agent": USER_AGENT}
    if headers:
        default_headers.update(headers)

    for attempt in range(retries):
        try:
            with httpx.Client(follow_redirects=follow_redirects, timeout=timeout) as client:
                resp = client.get(url, headers=default_headers)
                return resp
        except Exception as exc:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def cache_key(*parts: str) -> str:
    """Deterministic cache key from strings."""
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


def cache_read(key: str, ttl_hours: float) -> Any | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if time.time() - mtime > ttl_hours * 3600:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cache_write(key: str, data: Any) -> None:
    path = CACHE_DIR / f"{key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def evidence_fact(
    value: Any,
    source_url: str,
    method: str,
    collected_at: str | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "value": value,
        "source_url": source_url,
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "method": method,
    }


def evidence_error(error: str, source_url: str, method: str) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "value": None,
        "error": error,
        "source_url": source_url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "method": method,
    }
