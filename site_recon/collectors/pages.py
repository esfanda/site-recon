"""Page harvest: homepage, key pages, robots/sitemap, screenshot."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from site_recon.config import DATA_DIR
from site_recon.utils import cache_key, cache_read, cache_write, evidence_error, evidence_fact, http_get

KEYWORD_PAGES = [
    ("pricing", r"(pricing|plans|cost|quote)"),
    ("about", r"(about|story|team|who)"),
    ("contact", r"(contact|support|help)"),
    ("services", r"(services|products|solutions|features|offerings)"),
    ("blog", r"(blog|news|articles|insights|resources)"),
    ("case_studies", r"(case.stud|portfolio|work|clients|testimonials)"),
    ("terms", r"(terms|conditions|legal)"),
    ("privacy", r"(privacy|gdpr|cookie.policy)"),
    ("refund", r"(refund|return|money.back|guarantee)"),
    ("careers", r"(career|jobs|join.us|hiring)"),
    ("faq", r"(faq|frequently.asked)"),
]


def collect_pages(url: str, domain: str, use_playwright: bool = True, ttl_hours: float = 24.0) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    evidence["homepage"] = _fetch_homepage(url, domain, ttl_hours)
    evidence["key_pages"] = _discover_key_pages(url, domain, evidence["homepage"], ttl_hours)
    evidence["robots"] = _robots_txt(url, domain, ttl_hours)
    evidence["sitemap"] = _sitemap(url, domain, ttl_hours)
    if use_playwright:
        evidence["screenshot"] = _screenshot(url, domain)
    return evidence


def _fetch_homepage(url: str, domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("homepage", domain), ttl_hours)
    if cache is not None:
        return cache

    try:
        resp = http_get(url, timeout=20.0)
        final_url = str(resp.url)
        headers = dict(resp.headers)
        text = resp.text
        needs_playwright = len(text) < 2000 or ("<script" in text[:5000] and "<noscript" not in text[:5000])
        
        # If we got a non-OK status or need playwright, try playwright
        if resp.status_code >= 400 or needs_playwright:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    text = page.content()
                    title = page.title()
                    headers = {}  # Can't easily get headers from playwright
                    browser.close()
                fact = evidence_fact(
                    {
                        "final_url": url,
                        "status_code": 200,
                        "headers": headers,
                        "text_length": len(text),
                        "needs_playwright": False,
                        "html_snippet": text[:8000],
                        "playwright_used": True,
                        "title": title,
                    },
                    url,
                    "playwright_get",
                )
                cache_write(cache_key("homepage", domain), fact)
                return fact
            except Exception as pw_exc:
                # If playwright also fails, return the original httpx result
                pass
        
        fact = evidence_fact(
            {
                "final_url": final_url,
                "status_code": resp.status_code,
                "headers": headers,
                "text_length": len(text),
                "needs_playwright": needs_playwright,
                "html_snippet": text[:8000],
            },
            final_url,
            "httpx_get",
        )
        cache_write(cache_key("homepage", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), url, "httpx_get")
        cache_write(cache_key("homepage", domain), err)
        return err


def _discover_key_pages(base_url: str, domain: str, homepage_evidence: dict[str, Any], ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("keypages", domain), ttl_hours)
    if cache is not None:
        return cache

    html = (homepage_evidence.get("value") or {}).get("html_snippet", "")
    if not html:
        return evidence_error("no homepage html", base_url, "key_page_discovery")

    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        full = urljoin(base_url, href)
        for name, pattern in KEYWORD_PAGES:
            if name in found:
                continue
            if re.search(pattern, text) or re.search(pattern, href.lower()):
                found[name] = full

    pages: dict[str, Any] = {}
    for name, page_url in found.items():
        try:
            r = http_get(page_url, timeout=15.0)
            pages[name] = {
                "url": str(r.url),
                "status": r.status_code,
                "text_length": len(r.text),
                "title": _extract_title(r.text),
            }
        except Exception as exc:
            pages[name] = {"url": page_url, "error": str(exc)}

    fact = evidence_fact(pages, base_url, "key_page_discovery")
    cache_write(cache_key("keypages", domain), fact)
    return fact


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return m.group(1).strip() if m else None


def _robots_txt(base_url: str, domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("robots", domain), ttl_hours)
    if cache is not None:
        return cache

    robots_url = urljoin(base_url, "/robots.txt")
    try:
        r = http_get(robots_url, timeout=10.0)
        text = r.text
        sitemaps = re.findall(r"Sitemap:\s*(.+)", text, re.I)
        disallows = re.findall(r"Disallow:\s*(.+)", text, re.I)
        fact = evidence_fact(
            {"raw": text, "sitemaps": sitemaps, "disallows": disallows},
            robots_url,
            "robots_txt",
        )
        cache_write(cache_key("robots", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), robots_url, "robots_txt")
        cache_write(cache_key("robots", domain), err)
        return err


def _sitemap(base_url: str, domain: str, ttl_hours: float) -> dict[str, Any]:
    cache = cache_read(cache_key("sitemap", domain), ttl_hours)
    if cache is not None:
        return cache

    sitemap_url = urljoin(base_url, "/sitemap.xml")
    try:
        r = http_get(sitemap_url, timeout=15.0)
        text = r.text
        urls = re.findall(r"<loc>([^<]+)</loc>", text)
        lastmods = re.findall(r"<lastmod>([^<]+)</lastmod>", text)
        fact = evidence_fact(
            {"url_count": len(urls), "urls_sample": urls[:20], "lastmods": lastmods[:20]},
            sitemap_url,
            "sitemap_xml",
        )
        cache_write(cache_key("sitemap", domain), fact)
        return fact
    except Exception as exc:
        err = evidence_error(str(exc), sitemap_url, "sitemap_xml")
        cache_write(cache_key("sitemap", domain), err)
        return err


def _screenshot(url: str, domain: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    out_dir = DATA_DIR / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "homepage.png"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=str(path), full_page=True)
            browser.close()
        return evidence_fact(str(path), url, "playwright_screenshot")
    except Exception as exc:
        return evidence_error(str(exc), url, "playwright_screenshot")
