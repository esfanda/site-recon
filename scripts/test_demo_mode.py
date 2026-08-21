"""Phase 1 self-test: public demo isolation and no FIT/COLLAB."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"
os.environ["SITE_RECON_DEMO_KEY"] = "secret-demo-key-xyz"

from site_recon.analysts.runner import _combined_schema, run_analysts  # noqa: E402
from site_recon.config import data_dir, is_public_demo, reports_dir  # noqa: E402


def main() -> int:
    assert is_public_demo()
    assert "demo_data" in str(data_dir())
    assert "demo_data" in str(reports_dir())

    schema = _combined_schema("friend", public_demo=True)
    assert "fit_verdict" not in schema["properties"]
    assert "collab_brief" not in schema["properties"]

    evidence = {
        "meta": {"domain": "example.com", "collected_at": "2026-01-01T00:00:00Z"},
        "pages": {"visible_text": {"value": "Hello"}},
        "health": {},
        "tech_stack": {},
        "identity": {},
        "traction": {},
    }
    analysis = run_analysts(evidence, profile="SHOULD NOT BE USED", public_demo=True)
    assert "fit_verdict" not in analysis
    assert "collab_brief" not in analysis

    tmpl_path = ROOT / "site_recon/render/templates/report.md.j2"
    tmpl = tmpl_path.read_text(encoding="utf-8")
    assert "{% if not public_demo %}" in tmpl

    print("PASS: public demo isolation and no FIT/COLLAB in analysis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
