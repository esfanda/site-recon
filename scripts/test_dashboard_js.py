#!/usr/bin/env python3
"""The dashboard is one HTML file with the whole app inlined.

One unescaped apostrophe inside a translated string ends the script early
and the page renders blank, with the failure visible only in the browser
console. That shipped once, in a Turkish string, on 2026-08-21.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "dashboard" / "index.html"

# A single-quoted JS string literal on its own line: key, value, trailing comma.
STRING_LINE = re.compile(r"^\s*'[\w.]+':\s*'(.*)',\s*$")


def unescaped_quotes(html: str) -> list[tuple[int, str]]:
    bad = []
    for n, line in enumerate(html.splitlines(), 1):
        m = STRING_LINE.match(line)
        if not m:
            continue
        body = m.group(1)
        # Walk the body; a quote not preceded by a backslash closes the literal.
        for i, ch in enumerate(body):
            if ch == "'" and (i == 0 or body[i - 1] != "\\"):
                bad.append((n, line.strip()[:90]))
                break
    return bad


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")

    bad = unescaped_quotes(html)
    if bad:
        for n, line in bad:
            print(f"line {n}: unescaped ' in a JS string -> {line}", file=sys.stderr)
        print(f"FAIL: {len(bad)} translated string(s) would break the page", file=sys.stderr)
        return 1

    node = shutil.which("node")
    if node:
        blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
        js = "\n".join(b for b in blocks if "renderVibe" in b or "function setLang" in b)
        tmp = Path(tempfile.gettempdir()) / "site_recon_dashboard_check.js"
        tmp.write_text(js, encoding="utf-8")
        res = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            print("FAIL: dashboard JavaScript does not parse", file=sys.stderr)
            return 1
        print("PASS: no unescaped quotes, dashboard JavaScript parses")
        return 0

    print("PASS: no unescaped quotes (node not installed, skipped parse check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
