#!/usr/bin/env python3
"""A "no builder found" verdict has to show its work.

Erfan's complaint on 2026-08-21: the Vibe Code tab said "None" and nothing
else, so he could not tell a site that was checked and came back clean from
a builder the tool has never heard of.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_recon.collectors.vibe_code import collect_fingerprints  # noqa: E402


def evidence(html: str, host: str = "example.com", framework=None) -> dict:
    return {
        "meta": {"domain": host, "target_url": f"https://{host}"},
        "pages": {"homepage": {"value": {"html_snippet": html, "headers": {}, "final_url": f"https://{host}"}}},
        "tech_stack": {"value": {"cms_framework": framework or []}},
    }


def main() -> int:
    clean = collect_fingerprints(evidence("<html><h1>hi</h1></html>", framework=["Next.js"]))
    r = clean["reasoning"]
    assert clean["detected"] is False
    assert len(r["checked_builders"]) >= 7, r["checked_builders"]
    assert "Lovable" in r["checked_builders"] and "Bolt" in r["checked_builders"]
    assert r["builder_signal_count"] == 0
    assert r["matched_builders"] == []
    assert r["framework"] == ["Next.js"], r["framework"]
    # The honest limit must always travel with the verdict.
    assert "Cursor" in r["blind_spots"] and "Claude Code" in r["blind_spots"]

    hit = collect_fingerprints(evidence(
        '<div data-lov-id="x"></div><script src="https://cdn.gpteng.co/a.js"></script>'
    ))
    r2 = hit["reasoning"]
    assert hit["detected"] is True
    assert r2["matched_builders"] == ["Lovable"], r2["matched_builders"]
    assert r2["builder_signal_count"] >= 2
    assert "Cursor" in r2["blind_spots"], "the limit applies to positive verdicts too"

    stack = collect_fingerprints(evidence(
        '<script src="/assets/main-a1b2c3d4.js"></script>fetch("https://abc.supabase.co/x")'
    ))
    r3 = stack["reasoning"]
    assert stack["detected"] is False, "stack markers alone must not name a builder"
    found = {n["id"] for n in r3["stack_notes"]}
    assert found == {"supabase", "vite_hash"}, found

    print("PASS: verdicts carry what was checked, what matched, and what they cannot claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
