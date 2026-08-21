"""Phase 2 self-test: per-IP then global cap, zero subprocess once blocked."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"
os.environ["SITE_RECON_DEMO_KEY"] = "test-key-not-real"
os.environ["SITE_RECON_DEMO_SKIP_RUN"] = "1"

from dashboard import api as dashboard_api  # noqa: E402
from site_recon.demo import cap_message  # noqa: E402


def get(url: str, ip: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"CF-Connecting-IP": ip})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="site-recon-demo-cap-"))
    limits = tmp / "limits.yaml"
    limits.write_text("global_daily_cap: 3\nper_ip_daily_cap: 2\nretention_hours: 48\n", encoding="utf-8")
    os.environ["SITE_RECON_DEMO_LIMITS"] = str(limits)
    os.environ["SITE_RECON_DEMO_DB"] = str(tmp / "usage.sqlite")

    dashboard_api.PUBLIC_DEMO = True
    dashboard_api.SUBPROCESS_STARTS = 0
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.APIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    base = f"http://127.0.0.1:{port}"
    expected = cap_message()

    try:
        starts = dashboard_api.SUBPROCESS_STARTS
        for i in range(2):
            code, body = get(f"{base}/api/run?domain=ip-test-{i}.example", "203.0.113.10")
            assert code == 200, body
            assert body.get("status") == "started", body
        assert dashboard_api.SUBPROCESS_STARTS == starts

        code, body = get(f"{base}/api/run?domain=ip-test-3.example", "203.0.113.10")
        assert code == 429, body
        assert body.get("capped") is True
        assert body.get("cap") == "per_ip"
        assert expected in body.get("error", "")

        code, body = get(f"{base}/api/run?domain=other.example", "203.0.113.20")
        assert code == 200, body

        code, body = get(f"{base}/api/run?domain=global-block.example", "203.0.113.30")
        assert code == 429, body
        assert body.get("cap") == "global"

        code, body = get(f"{base}/api/demo-usage", "203.0.113.10")
        assert code == 200 and body.get("used") == 2

        print("PASS: per-IP and global caps block before any subprocess")
        return 0
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
