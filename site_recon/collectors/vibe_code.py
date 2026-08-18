"""Builder fingerprints (separate from craft score). No LLM."""
from __future__ import annotations

import re
from typing import Any

# Each rule is one signal. Verdict uses independent classes, not a single regex.
# Classes: host, cdn, dom, network, header.
# Do not name Cursor or Claude Code. They leave no stable public marker.
SIGNAL_RULES = [
    {"id": "lovable_host", "builder": "Lovable", "class": "host", "strength": "high",
     "pattern": r"[\w.-]*lovable\.app\b"},
    {"id": "lovable_uploads", "builder": "Lovable", "class": "cdn", "strength": "high",
     "pattern": r"lovable-uploads"},
    {"id": "gpteng_cdn", "builder": "Lovable", "class": "cdn", "strength": "high",
     "pattern": r"cdn\.gpteng\.co|gptengineer\.(?:js|app|co)"},
    {"id": "lovable_badge", "builder": "Lovable", "class": "dom", "strength": "high",
     "pattern": r"lovable-badge|made with lovable"},
    {"id": "data_lov_id", "builder": "Lovable", "class": "dom", "strength": "high",
     "pattern": r"data-lov-id|data-lovable"},
    {"id": "lovable_flock", "builder": "Lovable", "class": "network", "strength": "medium",
     "pattern": r"~flock\.js|/flock\.js|data-proxy-url=\"/~api/analytics\""},
    {"id": "bolt_host", "builder": "Bolt", "class": "host", "strength": "high",
     "pattern": r"[\w.-]*bolt\.new\b|[\w.-]*bolt\.host\b"},
    {"id": "stackblitz", "builder": "Bolt", "class": "cdn", "strength": "high",
     "pattern": r"stackblitz\.com"},
    {"id": "v0_host", "builder": "v0", "class": "host", "strength": "high",
     "pattern": r"[\w.-]*v0\.dev\b|[\w.-]*v0\.app\b"},
    {"id": "replit_host", "builder": "Replit", "class": "host", "strength": "high",
     "pattern": r"[\w.-]*replit\.(?:app|dev)\b|[\w.-]*repl\.co\b"},
    {"id": "base44_host", "builder": "Base44", "class": "host", "strength": "high",
     "pattern": r"[\w.-]*base44\.app\b|\bbase44\b"},
    {"id": "emergent_host", "builder": "Emergent", "class": "host", "strength": "high",
     "pattern": r"emergent\.sh"},
    {"id": "framer_cdn", "builder": "Framer", "class": "cdn", "strength": "high",
     "pattern": r"framerusercontent\.com|framer\.com"},
]

_STACK_NOTES = [
    {"id": "supabase", "builder": None, "class": "network", "strength": "medium",
     "pattern": r"supabase\.(?:co|in)"},
    {"id": "vite_hash", "builder": None, "class": "cdn", "strength": "low",
     "pattern": r"/assets/[\w-]+-[A-Za-z0-9_-]{6,}\.(?:css|js)"},
]

_BUILDER_ANALYTICS = {"Flock"}
_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}


def collect_fingerprints(evidence: dict[str, Any]) -> dict[str, Any]:
    blob = _search_blob(evidence)
    signals: list[dict[str, Any]] = []
    for rule in SIGNAL_RULES + _STACK_NOTES:
        match = re.search(rule["pattern"], blob, re.I)
        if not match:
            continue
        snippet = match.group(0)
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        signals.append({
            "id": rule["id"],
            "builder": rule["builder"],
            "class": rule["class"],
            "strength": rule["strength"],
            "evidence": snippet,
        })
    return _verdict(signals)


def _verdict(signals: list[dict[str, Any]]) -> dict[str, Any]:
    by_builder: dict[str, list[dict[str, Any]]] = {}
    for sig in signals:
        name = sig.get("builder")
        if not name:
            continue
        by_builder.setdefault(name, []).append(sig)

    builders: list[dict[str, Any]] = []
    for name, sigs in by_builder.items():
        classes = sorted({s["class"] for s in sigs if s["strength"] in ("high", "medium")})
        has_high = any(s["strength"] == "high" for s in sigs)
        if len(classes) >= 2 and has_high:
            confidence = "high"
        elif has_high:
            confidence = "medium"
        elif classes:
            confidence = "low"
        else:
            continue
        builders.append({"name": name, "confidence": confidence, "classes": classes})

    builders.sort(key=lambda b: _CONF_RANK[b["confidence"]], reverse=True)
    overall = builders[0]["confidence"] if builders else "none"
    detected = overall in ("high", "medium", "low")
    return {
        "detected": detected,
        "confidence": overall,
        "builders": [b["name"] for b in builders],
        "builder_detail": builders,
        "fingerprints": signals,
    }


def score_vibe_code(evidence: dict[str, Any]) -> dict[str, Any]:
    fp = collect_fingerprints(evidence)
    html = _search_blob(evidence)
    tech = _val(evidence.get("tech_stack")) or {}
    analytics = list(tech.get("analytics") or [])
    on_page = _nested(evidence, "health", "on_page") or {}
    crawl = _nested(evidence, "health", "crawl") or {}
    sitemap = _nested(evidence, "pages", "sitemap") or {}
    pagespeed = _nested(evidence, "health", "pagespeed") or {}

    checks: list[dict[str, Any]] = []
    weights = {
        "h1": 10, "schema": 5, "sitemap": 5, "builder_badge": 10, "preview_cdn": 8,
        "real_analytics": 4, "copyright": 2, "viewport": 6, "favicon": 3, "title": 3,
        "meta_description": 5, "og": 4, "twitter": 2, "alt": 5, "broken_links": 8,
        "performance": 8,
    }

    def add(cid: str, passed: bool, leftover: bool = False) -> None:
        checks.append({"id": cid, "pass": bool(passed), "leftover": leftover, "weight": weights.get(cid, 3)})

    add("viewport", bool(on_page.get("has_viewport")))
    add("favicon", bool(on_page.get("has_favicon")))
    add("title", bool(on_page.get("title")))
    add("meta_description", bool(on_page.get("meta_description")))
    add("h1", bool(on_page.get("h1")))
    add("og", bool(on_page.get("has_og")))
    add("twitter", bool(on_page.get("has_twitter_card")))
    add("alt", (on_page.get("images_without_alt") or 0) == 0)
    add("schema", bool(on_page.get("has_schema")))
    add("sitemap", int(sitemap.get("url_count") or 0) > 0)
    add("broken_links", len(crawl.get("broken") or []) == 0)
    add("copyright", bool(on_page.get("copyright_year")))

    badge = bool(re.search(r"lovable-badge|made with lovable|edit with bolt", html, re.I))
    preview_cdn = bool(re.search(r"lovable\.app|bolt\.new/|v0\.dev/", html, re.I))
    only_builder_analytics = bool(analytics) and all(a in _BUILDER_ANALYTICS for a in analytics)
    add("builder_badge", not badge, leftover=True)
    add("preview_cdn", not preview_cdn, leftover=True)
    add("real_analytics", not only_builder_analytics and bool(analytics), leftover=True)

    perf = (pagespeed.get("scores") or {}).get("performance")
    if isinstance(perf, (int, float)):
        add("performance", perf >= 0.5)

    craft = 85
    for c in checks:
        if not c["pass"]:
            craft -= c["weight"]
    craft = max(0, min(100, craft))
    if craft >= 80:
        grade = "shipready"
    elif craft >= 60:
        grade = "solid"
    elif craft >= 40:
        grade = "rough"
    else:
        grade = "sloppy"

    return {
        **fp,
        "craft_score": craft,
        "craft_grade": grade,
        "checks": checks,
    }


def _search_blob(evidence: dict[str, Any]) -> str:
    homepage = _nested(evidence, "pages", "homepage") or {}
    meta = evidence.get("meta") or {}
    headers = homepage.get("headers") or {}
    parts = [
        homepage.get("html_snippet") or "",
        homepage.get("final_url") or "",
        meta.get("target_url") or "",
        meta.get("domain") or "",
    ]
    for key, val in headers.items():
        parts.append(f"{key}: {val}")
    return "\n".join(str(p) for p in parts)


def _val(node: Any) -> Any:
    if isinstance(node, dict) and "value" in node:
        return node.get("value")
    return node if isinstance(node, dict) else {}


def _nested(evidence: dict[str, Any], *keys: str) -> Any:
    cur: Any = evidence
    for key in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key)
    return _val(cur)
