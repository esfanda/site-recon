#!/usr/bin/env python3
"""An H1 below the fold of the HTML must still be found.

erfandigital.com was reported as having no H1 while the tag sat plainly in
the markup. The collector kept only the first 8,000 characters, and a modern
framework's head is bigger than that on its own, so the check was reading a
document that stopped before the body got interesting.

A false "missing" is worse than no check: it sends someone off to fix
something that was never broken.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_recon.collectors.health import _on_page_checks  # noqa: E402
from site_recon.collectors.pages import HTML_FOR_CHECKS_LIMIT  # noqa: E402


def main() -> int:
    # A head large enough to bury the body, which is the ordinary case.
    filler = "<link rel='preload' href='/a.css'>" * 400
    html = (
        "<html lang='en'><head><title>T</title>"
        "<meta name='description' content='d'>"
        "<meta name='viewport' content='width=device-width'>"
        f"{filler}</head><body>"
        "<h1>I Don't Run Campaigns. I Engineer Growth.</h1>"
        "<script type='application/ld+json'>{\"@type\":\"Person\"}</script>"
        "</body></html>"
    )
    assert len(html) > 8000, "the fixture must be bigger than the old limit"

    # The collector wraps every result in an evidence envelope.
    checks = _on_page_checks("https://example.com", html)["value"]
    if not checks.get("h1"):
        print(f"FAIL: h1 missed in a {len(html)} character page", file=sys.stderr)
        return 1
    if not checks.get("has_schema"):
        print("FAIL: schema missed below the old cutoff", file=sys.stderr)
        return 1
    if HTML_FOR_CHECKS_LIMIT < 100_000:
        print(f"FAIL: the stored html limit is back down to {HTML_FOR_CHECKS_LIMIT}",
              file=sys.stderr)
        return 1

    print("PASS: h1 and schema found past the old 8k cutoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
