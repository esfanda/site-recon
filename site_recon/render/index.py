"""Render INDEX.md comparison table."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Template

from site_recon.config import REPORTS_DIR

INDEX_TEMPLATE = """# Site Recon Index

| Domain | Date Analyzed | Label | Fit Score | Top Pain Point | Next Action | Status |
|--------|---------------|-------|-----------|----------------|-------------|--------|
{% for row in rows %}
| {{ row.domain }} | {{ row.date }} | {{ row.label }} | {{ row.fit_score }} | {{ row.top_pain }} | {{ row.next_action }} | {{ row.status }} |
{% endfor %}
"""


def update_index(domain: str, analysis: dict[str, Any], status: str = "new") -> None:
    index_path = REPORTS_DIR / "INDEX.md"
    rows = []
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8")
        # parse existing rows
        for line in text.splitlines():
            if line.startswith("|") and "Domain" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 7:
                    rows.append({
                        "domain": parts[0],
                        "date": parts[1],
                        "label": parts[2],
                        "fit_score": parts[3],
                        "top_pain": parts[4],
                        "next_action": parts[5],
                        "status": parts[6],
                    })

    # dedupe by domain
    rows = [r for r in rows if r["domain"] != domain]

    pain_points = analysis.get("pain_points", {}).get("pain_points", [])
    top_pain = pain_points[0]["problem"][:60] if pain_points else "-"

    rows.append({
        "domain": domain,
        "date": analysis.get("meta", {}).get("collected_at", "")[:10],
        "label": analysis.get("fit_verdict", {}).get("label", "?"),
        "fit_score": analysis.get("fit_verdict", {}).get("fit_score", "?"),
        "top_pain": top_pain,
        "next_action": analysis.get("fit_verdict", {}).get("next_action", "?"),
        "status": status,
    })

    # sort by date desc
    rows.sort(key=lambda r: r["date"], reverse=True)

    tmpl = Template(INDEX_TEMPLATE)
    rendered = tmpl.render(rows=rows)
    index_path.write_text(rendered, encoding="utf-8")
