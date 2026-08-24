#!/usr/bin/env python3
"""The samples are the fallback for every other failure, so they must not fail.

They are what a visitor sees when the daily cap is spent, when the shared key
dies, or when they simply do not want to wait four minutes. If a sample is
blank or missing a language, the demo is back to the dead end these were built
to remove, only now it is silent about it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
LANGS = ["en", "fa", "tr", "ar"]
SECTIONS = ["claim_audit", "business_teardown", "pain_points", "hygiene"]

# Scored against Erfan's own profile. A public sample must not carry them.
PRIVATE_KEYS = ["fit_verdict", "outreach", "collab_brief"]


def main() -> int:
    index_path = SAMPLES / "index.json"
    if not index_path.is_file():
        print("FAIL: samples/index.json is missing", file=sys.stderr)
        return 1
    index = json.loads(index_path.read_text(encoding="utf-8"))
    domains = index.get("domains") or []
    if not domains:
        print("FAIL: no sample domains listed", file=sys.stderr)
        return 1

    problems = []
    for domain in domains:
        folder = SAMPLES / domain
        if not (folder / "evidence.json").is_file():
            problems.append(f"{domain}: evidence.json missing")
            continue
        try:
            json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{domain}: evidence.json will not parse ({exc})")

        for lang in LANGS:
            path = folder / f"analysis.{lang}.json"
            if not path.is_file():
                problems.append(f"{domain}/{lang}: missing")
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                problems.append(f"{domain}/{lang}: will not parse ({exc})")
                continue
            if not any(data.get(k) for k in SECTIONS):
                problems.append(f"{domain}/{lang}: every section is empty")
            for key in PRIVATE_KEYS:
                if data.get(key):
                    problems.append(f"{domain}/{lang}: leaks {key}")

    if problems:
        for line in problems:
            print("  " + line, file=sys.stderr)
        print(f"FAIL: {len(problems)} problem(s) across {len(domains)} sample(s)",
              file=sys.stderr)
        return 1

    print(f"PASS: {len(domains)} samples, {len(LANGS)} languages each, "
          f"all populated and free of profile data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
