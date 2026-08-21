"""Orchestrate all collectors into a single evidence.json."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from site_recon.collectors.health import collect_health
from site_recon.collectors.identity import collect_identity
from site_recon.collectors.pages import collect_pages
from site_recon.collectors.tech_stack import collect_tech_stack
from site_recon.collectors.vibe_code import score_vibe_code
from site_recon.collectors.traction import collect_traction
from site_recon.config import data_dir
from site_recon.utils import evidence_error


def run_all(url: str, use_playwright: bool = True, fast: bool = False) -> dict[str, Any]:
    parsed = __import__("urllib.parse").parse.urlparse(url)
    domain = parsed.netloc or parsed.path
    domain = domain.replace("www.", "", 1)

    out_dir = data_dir() / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, Any] = {
        "meta": {
            "target_url": url,
            "domain": domain,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "fast_mode": fast,
        }
    }

    # Layer A: deterministic collectors.
    #
    # identity, pages and traction each spend almost all of their time waiting
    # on other people's servers, and none of them reads the others' output, so
    # they run together. Only health and tech_stack need the fetched HTML, so
    # they wait. On a Raspberry Pi this is the difference between a demo that
    # answers and one that times out.
    with ThreadPoolExecutor(max_workers=3) as pool:
        identity_job = pool.submit(collect_identity, domain)
        pages_job = pool.submit(
            collect_pages, url, domain, use_playwright=use_playwright and not fast
        )
        traction_job = pool.submit(collect_traction, domain, domain.split(".")[0])
        evidence["identity"] = identity_job.result()
        evidence["pages"] = pages_job.result()
        evidence["traction"] = traction_job.result()

    homepage_ev = evidence["pages"].get("homepage", {})
    homepage_val = homepage_ev.get("value") or {}
    html = homepage_val.get("html_snippet", "")
    headers = homepage_val.get("headers", {})

    evidence["tech_stack"] = collect_tech_stack(html, headers)
    evidence["health"] = collect_health(url, domain, html)
    evidence["vibe_code"] = score_vibe_code(evidence)

    # Write evidence.json
    evidence_path = out_dir / "evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    return evidence
