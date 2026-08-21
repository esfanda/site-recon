#!/usr/bin/env python3
"""Reading the same report in another language must not cost a scan.

Erfan asked for the report to come back in whichever language is requested.
With a public cap of two scans a day, charging for the language re-run would
mean a visitor who picks the wrong language first can never see a second
site at all.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["SITE_RECON_DEMO_DB"] = str(Path(tempfile.mkdtemp()) / "usage.sqlite")
os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"

from site_recon.demo import check_and_record_scan, ip_scan_count  # noqa: E402


def main() -> int:
    ip = "203.0.113.44"

    ok, cap = check_and_record_scan(ip, "one.example")
    assert ok and cap is None
    assert ip_scan_count(ip) == 1

    # Same domain again, e.g. the visitor switched to Persian.
    for _ in range(3):
        ok, cap = check_and_record_scan(ip, "one.example")
        assert ok and cap is None, (ok, cap)
    assert ip_scan_count(ip) == 1, "language re-runs must not be charged"

    # A different domain still costs, and the cap still bites.
    ok, _ = check_and_record_scan(ip, "two.example")
    assert ok
    assert ip_scan_count(ip) == 2

    ok, cap = check_and_record_scan(ip, "three.example")
    assert not ok and cap == "per_ip", (ok, cap)

    # Still free to revisit either domain already scanned.
    ok, cap = check_and_record_scan(ip, "one.example")
    assert ok and cap is None

    print("PASS: language re-runs are free, new domains still counted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
