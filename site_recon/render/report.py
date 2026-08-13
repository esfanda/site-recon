"""Render single domain report from evidence + analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from site_recon.config import DATA_DIR, REPORTS_DIR
from site_recon.render.index import update_index


def render_report(domain: str, evidence: dict[str, Any], analysis: dict[str, Any], status: str = "new") -> Path:
    tmpl_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)))
    tmpl = env.get_template("report.md.j2")

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
        "fit_verdict": analysis.get("fit_verdict", {}),
        "outreach": analysis.get("outreach"),
        "collab_brief": analysis.get("collab_brief"),
    }

    rendered = tmpl.render(**context)
    report_path = REPORTS_DIR / f"{domain}.md"
    report_path.write_text(rendered, encoding="utf-8")

    # Also write JSON
    json_path = REPORTS_DIR / f"{domain}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"evidence": evidence, "analysis": analysis}, f, ensure_ascii=False, indent=2)

    update_index(domain, {**analysis, "meta": evidence.get("meta", {})}, status=status)
    return report_path
