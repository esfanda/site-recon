#!/usr/bin/env python3
"""Freeze three real reports into the repo so the demo has something to show.

A visitor lands on the public demo, picks a domain, and then stares at a
progress bar for four minutes before seeing anything. If the daily cap is
already spent they see nothing at all. Either way they leave without ever
learning what the tool does.

These samples answer that: a complete report, in their own language, in the
time it takes to click. They are ordinary output from an ordinary run, saved
to disk, so the public demo can serve them without a key, without a scan, and
without spending anyone's quota.

Run locally with a real key. Collectors run once per domain; the language
variants reuse that evidence and only re-run the analysts.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
DATA = ROOT / "data"

DOMAINS = ["avaautomate.com", "erfandigital.com", "menapark.com"]
LANGS = ["en", "fa", "tr", "ar"]

# The model is rate limited and occasionally returns nothing usable. Back off
# and try again rather than shipping a blank sample, which is the exact failure
# these samples exist to prevent.
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = [30, 60, 120, 240]


def run(args: list[str], timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "site_recon.cli", *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def analysis_is_usable(path: Path) -> bool:
    """A file can exist and still say nothing. Check for actual content."""
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return any(data.get(k) for k in
               ("claim_audit", "business_teardown", "pain_points", "hygiene"))


def build(domain: str) -> bool:
    print(f"\n=== {domain} ===", flush=True)
    out = DATA / domain

    # 1. evidence, once
    for attempt in range(1, MAX_ATTEMPTS + 1):
        code, log = run(["run", f"https://{domain}", "--lang", "en"])
        if analysis_is_usable(out / "analysis.en.json"):
            print(f"  en  ok", flush=True)
            break
        wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
        print(f"  en  attempt {attempt} failed (rc={code}), waiting {wait}s", flush=True)
        print("      " + log.strip().splitlines()[-1][:160] if log.strip() else "", flush=True)
        if attempt == MAX_ATTEMPTS:
            return False
        time.sleep(wait)

    # 2. the other languages reuse the evidence we just collected
    for lang in LANGS:
        if lang == "en":
            continue
        target = out / f"analysis.{lang}.json"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if analysis_is_usable(target):
                break
            code, log = run(["run", f"https://{domain}", "--lang", lang, "--llm-only"])
            if analysis_is_usable(target):
                break
            wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
            print(f"  {lang}  attempt {attempt} failed (rc={code}), waiting {wait}s", flush=True)
            if attempt == MAX_ATTEMPTS:
                return False
            time.sleep(wait)
        print(f"  {lang}  ok", flush=True)
    return True


def freeze(domain: str) -> None:
    """Copy the finished run into samples/, leaving out anything personal."""
    src, dst = DATA / domain, SAMPLES / domain
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "evidence.json", dst / "evidence.json")
    for lang in LANGS:
        shutil.copy2(src / f"analysis.{lang}.json", dst / f"analysis.{lang}.json")
    # FIT and the outreach draft are scored against Erfan's own profile and
    # have no business being in a public sample.
    for lang in LANGS:
        p = dst / f"analysis.{lang}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for key in ("fit_verdict", "outreach", "collab_brief"):
            data.pop(key, None)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    shot = src / "homepage.png"
    if shot.is_file():
        shutil.copy2(shot, dst / "homepage.png")
    print(f"  frozen -> samples/{domain}", flush=True)


def main() -> int:
    SAMPLES.mkdir(exist_ok=True)
    failed = []
    for domain in DOMAINS:
        if build(domain):
            freeze(domain)
        else:
            failed.append(domain)
    index = {"domains": [d for d in DOMAINS if d not in failed], "langs": LANGS}
    (SAMPLES / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + ("FAILED: " + ", ".join(failed) if failed else "all samples built"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
