#!/usr/bin/env python3
"""Owner allowlist must survive a rotating home IPv6.

Found on 2026-08-21: Erfan hit "today's free demo scans are used up" on his
own demo, because the allowlist matched exact addresses and his ISP hands
out a new IPv6 host part every few hours.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["SITE_RECON_DEMO_OWNER_IPS"] = "2a00:1d34:58fe:c100::/64,100.64.0.0/10,203.0.113.7"
os.environ["SITE_RECON_DEMO_OWNER_CAP"] = "10"

from site_recon.demo import ip_daily_cap, is_owner_ip  # noqa: E402


def main() -> int:
    owner = [
        "2a00:1d34:58fe:c100:84f3:d8ed:29f:4b0e",   # home, one host part
        "2a00:1d34:58fe:c100:2d23:5db7:6ea3:6d34",  # home, after rotation
        "100.67.93.87",                             # tailnet
        "203.0.113.7",                              # plain address entry
    ]
    stranger = ["2a00:1d34:58fe:c200::1", "8.8.8.8", "203.0.113.8", "not-an-ip", ""]

    for ip in owner:
        assert ip_daily_cap(ip) == 10, f"{ip} should get the owner cap"
    for ip in stranger:
        assert ip_daily_cap(ip) == 2, f"{ip} should get the public cap"

    for ip in owner:
        assert is_owner_ip(ip), f"{ip} should count as owner"
    for ip in stranger:
        assert not is_owner_ip(ip), f"{ip} should not count as owner"

    print("PASS: owner prefixes match across IPv6 rotation, strangers still capped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
