"""Traction proxies: Tranco, HN, Reddit, Trustpilot, social, ads."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from site_recon.utils import cache_key, cache_read, cache_write, evidence_error, evidence_fact, http_get

TRANCO_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "tranco_top1m.csv"


def _ensure_tranco() -> dict[str, int]:
    if not TRANCO_CSV.exists():
        _download_tranco()
    ranks: dict[str, int] = {}
    if TRANCO_CSV.exists():
        with open(TRANCO_CSV, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    try:
                        ranks[parts[1].lower()] = int(parts[0])
                    except ValueError:
                        pass
    return ranks


def _download_tranco() -> None:
    url = "https://tranco-list.eu/top-1m.csv.zip"
    try:
        import zipfile
        import io
        r = http_get(url, timeout=60.0)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = z.namelist()[0]
        TRANCO_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(TRANCO_CSV, "wb") as f:
            f.write(z.read(name))
    except Exception:
        pass


def collect_traction(domain: str, brand: str, ttl_hours: float = 72.0) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    evidence["tranco"] = _tranco_rank(domain)
    evidence["hacker_news"] = _hn_mentions(domain, ttl_hours)
    evidence["reddit"] = _reddit_mentions(domain, ttl_hours)
    evidence["trustpilot"] = _trustpilot(domain, ttl_hours)
    evidence["web_mentions"] = _web_mentions(domain, ttl_hours)
    evidence["social"] = {"value": "skipped", "note": "requires_playwright"}
    evidence["ads"] = {"value": "skipped", "note": "requires_playwright"}
    return evidence


def _tranco_rank(domain: str) -> dict[str, Any]:
    ranks = _ensure_tranco()
    rank = ranks.get(domain.lower())
    return evidence_fact(rank, "https://tranco-list.eu", "tranco_offline_lookup")


def _hn_mentions(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("hn", domain), ttl_hours)
    if cache is not None:
        return cache
    url = f"https://hn.algolia.com/api/v1/search?query={domain}&hitsPerPage=20"
    try:
        r = http_get(url, timeout=15.0)
        data = r.json()
        hits = data.get("hits", [])
        result = {
            "count": len(hits),
            "top": [
                {"title": h.get("title"), "url": h.get("url"), "points": h.get("points")}
                for h in hits[:5]
            ],
        }
        fact = evidence_fact(result, url, "hn_algolia_api")
        cache_write(cache_key("hn", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "hn_algolia_api")
        cache_write(cache_key("hn", domain), err)
        return err


def _reddit_mentions(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("reddit", domain), ttl_hours)
    if cache is not None:
        return cache
    url = f"https://www.reddit.com/search.json?q=%22{domain}%22&sort=new&limit=20"
    try:
        r = http_get(url, headers={"User-Agent": "SiteReconBot/1.0"}, timeout=15.0)
        data = r.json()
        posts = data.get("data", {}).get("children", [])
        result = {
            "count": len(posts),
            "recent": [
                {
                    "title": p.get("data", {}).get("title"),
                    "subreddit": p.get("data", {}).get("subreddit"),
                    "url": "https://reddit.com" + p.get("data", {}).get("permalink", ""),
                }
                for p in posts[:5]
            ],
        }
        fact = evidence_fact(result, url, "reddit_search_api")
        cache_write(cache_key("reddit", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "reddit_search_api")
        cache_write(cache_key("reddit", domain), err)
        return err


def _trustpilot(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("trustpilot", domain), ttl_hours)
    if cache is not None:
        return cache
    url = f"https://www.trustpilot.com/review/{domain}"
    try:
        r = http_get(url, timeout=15.0)
        text = r.text
        rating_match = re.search(r'"ratingValue"\s*:\s*"?([0-9.]+)"?', text)
        count_match = re.search(r'"reviewCount"\s*:\s*"?([0-9,]+)"?', text)
        rating = float(rating_match.group(1)) if rating_match else None
        count = int(count_match.group(1).replace(",", "")) if count_match else None
        # grab negative review snippets
        reviews = re.findall(r'<p[^>]*class="[^"]*typography_body__[^"]*"[^>]*>(.*?)</p>', text)
        negatives = [re.sub(r"<[^>]+>", "", v).strip() for v in reviews[:3]]
        result = {"rating": rating, "review_count": count, "negative_snippets": negatives}
        fact = evidence_fact(result, url, "trustpilot_public_page")
        cache_write(cache_key("trustpilot", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "trustpilot_public_page")
        cache_write(cache_key("trustpilot", domain), err)
        return err


def _web_mentions(domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("webmentions", domain), ttl_hours)
    if cache is not None:
        return cache
    query = f"\"{domain}\""
    url = f"https://html.duckduckgo.com/html/?q={query}"
    try:
        r = http_get(url, timeout=15.0)
        text = r.text
        links = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', text)
        titles = re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', text)
        result = {
            "count": len(links),
            "top": [
                {"title": re.sub(r"<[^>]+>", "", t).strip(), "url": u}
                for t, u in zip(titles[:5], links[:5])
            ],
        }
        fact = evidence_fact(result, url, "duckduckgo_html")
        cache_write(cache_key("webmentions", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "duckduckgo_html")
        cache_write(cache_key("webmentions", domain), err)
        return err
