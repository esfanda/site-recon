"""Render single domain report from evidence + analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from site_recon.config import is_public_demo, reports_dir
from site_recon.render.index import update_index


def render_report(domain: str, evidence: dict[str, Any], analysis: dict[str, Any], status: str = "new", lang: str = "en") -> Path:
    tmpl_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))
    tmpl = env.get_template("report.md.j2")

    public_demo = is_public_demo()
    context = {
        "domain": domain,
        "meta": evidence.get("meta", {}),
        "evidence": {k: v for k, v in evidence.items() if k != "meta"},
        "identity": evidence.get("identity", {}),
        "pages": evidence.get("pages", {}),
        "tech_stack": evidence.get("tech_stack", {}),
        "traction": evidence.get("traction", {}),
        "health": evidence.get("health", {}),
        "claim_audit": analysis.get("claim_audit", {}),
        "business_teardown": analysis.get("business_teardown", {}),
        "pain_points": analysis.get("pain_points", {}),
        "hygiene": analysis.get("hygiene", {}),
        "public_demo": public_demo,
        "fit_verdict": {} if public_demo else analysis.get("fit_verdict", {}),
        "outreach": None if public_demo else analysis.get("outreach"),
        "collab_brief": None if public_demo else analysis.get("collab_brief"),
    }

    rendered = tmpl.render(**context)
    suffix = "" if lang == "en" else f".{lang}"
    report_path = reports_dir() / f"{domain}{suffix}.md"
    report_path.write_text(rendered, encoding="utf-8")

    json_path = reports_dir() / f"{domain}{suffix}.json"
    out_analysis = analysis
    if public_demo:
        out_analysis = {k: v for k, v in analysis.items() if k not in ("fit_verdict", "collab_brief", "outreach")}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"evidence": evidence, "analysis": out_analysis}, f, ensure_ascii=False, indent=2)

    if not public_demo:
        update_index(domain, {**analysis, "meta": evidence.get("meta", {})}, status=status)
    return report_path
