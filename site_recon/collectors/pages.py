"""Page harvest: homepage, key pages, robots/sitemap, screenshot."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from site_recon.config import data_dir
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
                        **extract_rendered(text, url),
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
                **extract_rendered(text, final_url),
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

    hp = homepage_evidence.get("value") or {}
    links = hp.get("links")
    if not links:
        html = hp.get("html_snippet", "")
        if not html:
            return evidence_error("no homepage html", base_url, "key_page_discovery")
        soup = BeautifulSoup(html, "html.parser")
        links = [{"href": a["href"], "text": a.get_text(strip=True)} for a in soup.find_all("a", href=True)]

    found: dict[str, str] = {}
    for link in links:
        href = link.get("href", "")
        text = (link.get("text") or "").lower()
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

    out_dir = data_dir() / domain
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


# --- Rendered-content extraction -------------------------------------------
# The LLM used to receive only raw HTML, truncated to 8000 chars. On any
# client-rendered site (Vite, Next, Lovable) that is markup and script tags,
# not content, so the analyst never saw the actual page. These helpers pull
# out what a visitor sees.

AUTH_PATTERNS = [
    ("google", r"(sign|log|join|continue).{0,12}(in|up|with).{0,12}google|google.{0,12}(sign|log)"),
    ("microsoft", r"(microsoft|outlook|azure ad|entra)"),
    ("apple", r"(sign|log|continue).{0,12}(in|up|with).{0,12}apple"),
    ("github", r"(sign|log|continue).{0,12}(in|up|with).{0,12}github"),
    ("linkedin", r"(sign|log|continue).{0,12}(in|up|with).{0,12}linkedin"),
    ("email_password", r"(email address|password|e-mail).{0,40}(password|sign|log)|password"),
]

BUILDER_BADGE_PATTERNS = [
    ("Lovable", r"edit with lovable|lovable\.dev/projects|gpteng\.co"),
    ("Bolt", r"(built|made) with bolt|bolt\.new"),
    ("v0", r"built with v0|v0\.dev"),
    ("Framer", r"made in framer"),
    ("Wix", r"this site was (created|designed) with"),
    ("Replit", r"built on replit|replit\.app"),
]


def extract_rendered(html: str, base_url: str = "") -> dict[str, Any]:
    """Turn raw HTML into what a human actually sees on the page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))

    headings = [
        {"level": h.name, "text": h.get_text(" ", strip=True)[:200]}
        for h in soup.find_all(["h1", "h2", "h3"])
        if h.get_text(strip=True)
    ]

    cta_texts: list[str] = []
    for el in soup.find_all(["button", "a"]):
        label = el.get_text(" ", strip=True)
        if label and 2 <= len(label) <= 60:
            cta_texts.append(label)
    # keep order, drop duplicates
    seen: set[str] = set()
    cta_texts = [c for c in cta_texts if not (c.lower() in seen or seen.add(c.lower()))][:60]

    links = [
        {"href": a["href"], "text": a.get_text(" ", strip=True)[:80]}
        for a in soup.find_all("a", href=True)
    ][:400]

    haystack = (text + " " + " ".join(cta_texts)).lower()
    auth_providers = [name for name, pat in AUTH_PATTERNS if re.search(pat, haystack)]

    badges = [name for name, pat in BUILDER_BADGE_PATTERNS if re.search(pat, html, re.I)]

    return {
        "visible_text": text[:20000],
        "visible_text_length": len(text),
        "headings": headings[:60],
        "cta_texts": cta_texts,
        "auth_providers": auth_providers,
        "signup_is_single_provider": len(auth_providers) == 1,
        "visible_builder_badge": badges,
        "links": links,
        "empty_sections": _empty_sections(soup),
    }


def _empty_sections(soup: Any) -> list[str]:
    """Headings that promise content and have almost none under them.

    A community site that renders 'Open discussions' with nothing beneath it
    is telling every visitor the place is dead. That is a business finding,
    and no generic on-page checker will ever catch it.

    A heading's section is the largest ancestor that still contains no OTHER
    heading of the same level. Descendant headings of a deeper level (card
    titles under a section title) count as content, not as a boundary.
    """
    skip_zones = {"nav", "header", "footer", "aside", "form", "button", "a", "label"}
    empties: list[str] = []
    for h in soup.find_all(["h2", "h3"]):
        label = h.get_text(" ", strip=True)
        if not label:
            continue
        # Tab labels, link cards and chrome headings are not empty sections.
        if any(p.name in skip_zones for p in h.parents if p.name):
            continue
        section = h
        node = h.parent
        for _ in range(6):
            if node is None or node.name in ("body", "html"):
                break
            if len(node.find_all(h.name)) > 1:
                break
            section = node
            node = node.parent
        body = section.get_text(" ", strip=True).replace(label, " ")
        body = re.sub(r"\b(see all|view all|show more|browse|listed)\b", "", body, flags=re.I)
        if len(re.sub(r"[\s\d]+", " ", body).strip()) < 25:
            empties.append(label)
    return empties[:15]
