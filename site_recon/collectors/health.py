"""Technical health: PageSpeed, crawl, on-page checks."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from site_recon.config import get_pagespeed_key
from site_recon.utils import cache_key, cache_read, cache_write, evidence_error, evidence_fact, http_get


def collect_health(url: str, domain: str, homepage_html: str, ttl_hours: float = 24.0) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    evidence["pagespeed"] = _pagespeed(url, ttl_hours)
    evidence["on_page"] = _on_page_checks(url, homepage_html)
    evidence["crawl"] = _crawl(url, domain, homepage_html, ttl_hours)
    return evidence


def _pagespeed(url: str, ttl_hours: float) -> dict[str, Any]:
    key = cache_key("pagespeed", url)
    cache = cache_read(key, ttl_hours)
    if cache is not None:
        return cache
    api_key = get_pagespeed_key()
    api_url = (
        f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={url}&strategy=mobile&category=PERFORMANCE&category=SEO&category=ACCESSIBILITY"
    )
    request_url = api_url + (f"&key={api_key}" if api_key else "")
    if not api_key:
        # Anonymous quota for this API is 0/day. Fail fast with a clear
        # reason instead of a silent all-null result three retries later.
        # Do not cache no_key: operator may add SITE_RECON_DEMO_PAGESPEED_KEY
        # (or a local key) later in the same TTL window.
        return evidence_error(
            "no_key: PageSpeed needs a free Google API key (PAGESPEED_API_KEY "
            "env var or config/secrets.yaml pagespeed_api_key). Anonymous "
            "requests have a 0/day quota.",
            api_url,
            "pagespeed_insights_api",
        )
    try:
        r = http_get(request_url, timeout=60.0)
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "PageSpeed API error"))
        lighthouse = data.get("lighthouseResult", {})
        scores = {}
        for cat in ["performance", "seo", "accessibility"]:
            scores[cat] = lighthouse.get("categories", {}).get(cat, {}).get("score")
        audits = lighthouse.get("audits", {})
        metrics = {
            "lcp": audits.get("largest-contentful-paint", {}).get("numericValue"),
            "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
            "tbt": audits.get("total-blocking-time", {}).get("numericValue"),
        }
        result = {"scores": scores, "metrics": metrics}
        fact = evidence_fact(result, api_url, "pagespeed_insights_api")
        cache_write(key, fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), api_url, "pagespeed_insights_api")
        cache_write(key, err)
        return err


def probe_pagespeed_key(api_key: str) -> tuple[bool, str]:
    """Hit PageSpeed with a known-fast URL to check a key. Do not echo it."""
    key = (api_key or "").strip()
    if not key:
        return False, "No API key"
    test_url = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url=https://example.com&strategy=mobile&category=PERFORMANCE&key={key}"
    )
    try:
        r = http_get(test_url, timeout=30.0)
        data = r.json()
    except Exception:
        return False, "Could not reach PageSpeed. Try again."
    if "error" in data:
        msg = data["error"].get("message", "")
        if "API key not valid" in msg or "API_KEY_INVALID" in msg:
            return False, "This key was rejected. Paste a new key from the link above."
        if "has not been used" in msg or "disabled" in msg.lower():
            return False, "Enable the PageSpeed Insights API for this key's project, then try again."
        return False, msg or "PageSpeed rejected this key."
    return True, ""


def _on_page_checks(url: str, html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    checks: dict[str, Any] = {}

    checks["has_viewport"] = bool(soup.find("meta", attrs={"name": "viewport"}))
    checks["has_favicon"] = bool(soup.find("link", rel=re.compile(r"icon", re.I)))
    title_tag = soup.find("title")
    checks["title"] = title_tag.get_text(strip=True) if title_tag else None
    checks["meta_description"] = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        checks["meta_description"] = meta_desc.get("content")
    h1 = soup.find("h1")
    checks["h1"] = h1.get_text(strip=True) if h1 else None
    checks["images_without_alt"] = len([img for img in soup.find_all("img") if not img.get("alt")])
    checks["has_og"] = bool(soup.find("meta", property=re.compile(r"^og:")))
    checks["has_twitter_card"] = bool(soup.find("meta", attrs={"name": re.compile(r"^twitter:")}))
    checks["has_schema"] = "application/ld+json" in html
    checks["has_sitemap_link"] = "sitemap.xml" in html
    checks["has_robots_link"] = "robots.txt" in html
    # copyright year
    copyright_match = re.search(r"©\s*(\d{4})", html)
    checks["copyright_year"] = int(copyright_match.group(1)) if copyright_match else None
    # forms
    forms = soup.find_all("form")
    checks["form_count"] = len(forms)
    # cookie notice
    checks["has_cookie_notice"] = bool(
        soup.find(string=re.compile(r"cookie", re.I)) or "cookie" in html.lower()[:20000]
    )
    # lang
    html_tag = soup.find("html")
    checks["html_lang"] = html_tag.get("lang") if html_tag else None

    return evidence_fact(checks, url, "on_page_parsing")


def _crawl(base_url: str, domain: str, homepage_html: str, ttl_hours: float) -> dict[str, Any]:
    key = cache_key("crawl", domain)
    cache = cache_read(key, ttl_hours)
    if cache is not None:
        return cache

    soup = BeautifulSoup(homepage_html, "html.parser")
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc == domain or parsed.netloc == f"www.{domain}" or parsed.netloc == domain.replace("www.", ""):
            links.add(full)

    checked = []
    broken = []
    redirects = []
    for link in list(links)[:60]:
        try:
            r = http_get(link, follow_redirects=False, timeout=10.0)
            if r.status_code >= 400:
                broken.append({"url": link, "status": r.status_code})
            elif r.status_code in (301, 302, 307, 308):
                redirects.append({"url": link, "status": r.status_code, "location": r.headers.get("location")})
            checked.append({"url": link, "status": r.status_code})
        except Exception as exc:
            broken.append({"url": link, "error": str(exc)})

    result = {"checked": len(checked), "broken": broken, "redirects": redirects}
    fact = evidence_fact(result, base_url, "crawl_depth_1")
    cache_write(key, fact)
    return fact
