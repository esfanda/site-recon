#!/usr/bin/env python3
"""Simple HTTP API server for Site Recon Dashboard.

Serves the dashboard static files AND provides API endpoints to:
- Run recon on a domain
- Check recon status
- Get recon results
"""

import json
import os
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Paths
DASHBOARD_DIR = Path(__file__).parent
PROJECT_DIR = DASHBOARD_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from site_recon.collectors.health import probe_pagespeed_key  # noqa: E402
from site_recon.collectors.vibe_code import score_vibe_code  # noqa: E402
from site_recon.config import get_deepseek_key, get_gemini_key, get_pagespeed_key, load_sources, save_secrets, settings_public  # noqa: E402
from site_recon.llm import probe_key  # noqa: E402

# In-memory job tracking
jobs = {}  # domain -> {"status": "running|done|error", "started": timestamp, "ended": timestamp, "error": str}


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # API endpoints
        if path == "/api/run":
            self.handle_run(query)
            return
        elif path == "/api/status":
            self.handle_status(query)
            return
        elif path == "/api/results":
            self.handle_results(query)
            return
        elif path == "/api/domains":
            self.handle_domains()
            return
        elif path == "/api/settings":
            self.handle_settings_get()
            return

        # Static files (default behavior)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings":
            self.handle_settings_save()
            return
        if parsed.path == "/api/pagespeed-key":
            self.handle_pagespeed_key_save()
            return
        self.send_json({"error": "Not found"}, 404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def handle_run(self, query):
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return

        # Normalize domain
        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        # Check if already running
        if domain in jobs and jobs[domain]["status"] == "running":
            self.send_json({"status": "running", "domain": domain, "message": "Recon already in progress"})
            return

        # Start recon in background.
        # Reuse evidence.json (llm-only) only while it's still fresh by the
        # same TTL page_harvest already uses. Older than that, re-collect for
        # real - otherwise "Analyze" would silently keep showing a stale
        # screenshot and evidence forever, no matter how long ago it ran.
        ev_path = DATA_DIR / domain / "evidence.json"
        llm_only = False
        if ev_path.exists():
            ttl_hours = load_sources().get("collectors", {}).get("page_harvest", {}).get("ttl_hours", 24)
            age_hours = (time.time() - ev_path.stat().st_mtime) / 3600
            llm_only = age_hours < ttl_hours
        jobs[domain] = {
            "status": "running",
            "started": time.time(),
            "ended": None,
            "error": None,
            "mode": "llm-only" if llm_only else "full",
        }

        def run_recon():
            try:
                cmd = [sys.executable, "-m", "site_recon.cli", "run", f"https://{domain}", "--relationship", "friend"]
                if llm_only:
                    cmd.append("--llm-only")
                result = subprocess.run(
                    cmd,
                    cwd=str(PROJECT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes
                )
                if result.returncode == 0:
                    jobs[domain]["status"] = "done"
                else:
                    jobs[domain]["status"] = "error"
                    err = (result.stderr or result.stdout or "Unknown error").strip()
                    last = [ln for ln in err.splitlines() if ln.strip()]
                    jobs[domain]["error"] = last[-1] if last else "Unknown error"
            except subprocess.TimeoutExpired:
                jobs[domain]["status"] = "error"
                jobs[domain]["error"] = "Timeout after 5 minutes"
            except Exception as e:
                jobs[domain]["status"] = "error"
                jobs[domain]["error"] = str(e)
            finally:
                jobs[domain]["ended"] = time.time()

        import threading
        thread = threading.Thread(target=run_recon, daemon=True)
        thread.start()

        self.send_json({"status": "started", "domain": domain, "message": "Recon started"})

    def handle_status(self, query):
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return

        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        if domain not in jobs:
            # Check if data exists
            evidence_file = DATA_DIR / domain / "evidence.json"
            if evidence_file.exists():
                self.send_json({"status": "done", "domain": domain, "has_data": True})
            else:
                self.send_json({"status": "not_started", "domain": domain, "has_data": False})
            return

        job = jobs[domain]
        response = {
            "status": job["status"],
            "domain": domain,
            "started": job["started"],
            "elapsed": time.time() - job["started"] if job["ended"] is None else job["ended"] - job["started"],
            "mode": job.get("mode") or "full",
        }
        if job["error"]:
            response["error"] = job["error"]
        self.send_json(response)

    def handle_results(self, query):
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return

        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        evidence_file = DATA_DIR / domain / "evidence.json"
        analysis_file = DATA_DIR / domain / "analysis.json"

        result = {"domain": domain, "evidence": None, "analysis": None}

        if evidence_file.exists():
            try:
                with open(evidence_file, "r", encoding="utf-8") as f:
                    result["evidence"] = json.load(f)
            except Exception as e:
                result["evidence_error"] = str(e)

        if analysis_file.exists():
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    result["analysis"] = json.load(f)
            except Exception as e:
                result["analysis_error"] = str(e)

        if result["evidence"] is None and result["analysis"] is None:
            self.send_json({"error": f"No data found for {domain}. Run recon first."}, 404)
            return

        if result["evidence"]:
            result["vibe_code"] = score_vibe_code(result["evidence"])

        self.send_json(result)

    def handle_domains(self):
        domains = []
        if DATA_DIR.exists():
            for d in DATA_DIR.iterdir():
                if d.is_dir() and (d / "evidence.json").exists():
                    domains.append(d.name)
        self.send_json({"domains": domains})

    def handle_settings_get(self):
        self.send_json(settings_public())

    def handle_settings_save(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 8192:
            self.send_json({"error": "Payload too large"}, 400)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return
        provider = (body.get("provider") or "gemini").strip().lower()
        if provider not in ("gemini", "deepseek"):
            self.send_json({"error": "Provider must be gemini or deepseek"}, 400)
            return
        api_key = body.get("api_key")
        if api_key is not None:
            api_key = str(api_key).strip()
            if "\n" in api_key or len(api_key) > 200:
                self.send_json({"error": "Invalid API key"}, 400)
                return
        check_key = api_key if api_key else (
            get_gemini_key() if provider == "gemini" else get_deepseek_key()
        )
        if not check_key:
            save_secrets({"preferred_provider": provider})
            out = settings_public()
            out["ok"] = False
            out["error"] = "No API key"
            self.send_json(out)
            return
        ok, err = probe_key(provider, check_key)
        if not ok:
            if not api_key:
                save_secrets({"preferred_provider": provider})
            out = settings_public()
            out["ok"] = False
            out["error"] = err
            self.send_json(out, 400)
            return
        updates = {"preferred_provider": provider}
        if api_key:
            updates[f"{provider}_api_key"] = api_key
        save_secrets(updates)
        out = settings_public()
        out["ok"] = True
        self.send_json(out)


    def handle_pagespeed_key_save(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 8192:
            self.send_json({"error": "Payload too large"}, 400)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return
        api_key = body.get("api_key")
        if api_key is not None:
            api_key = str(api_key).strip()
            if "\n" in api_key or len(api_key) > 200:
                self.send_json({"error": "Invalid API key"}, 400)
                return
        check_key = api_key if api_key else get_pagespeed_key()
        if not check_key:
            out = settings_public()
            out["ok"] = False
            out["error"] = "No API key"
            self.send_json(out)
            return
        ok, err = probe_pagespeed_key(check_key)
        if not ok:
            out = settings_public()
            out["ok"] = False
            out["error"] = err
            self.send_json(out, 400)
            return
        if api_key:
            save_secrets({"pagespeed_api_key": api_key})
        out = settings_public()
        out["ok"] = True
        self.send_json(out)


def run_server(port=8080):
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("", port), APIHandler)
    print(f"Site Recon Dashboard API running at http://localhost:{port}", flush=True)
    print(f"Dashboard: http://localhost:{port}")
    print(f"API endpoints:")
    print(f"  GET /api/run?domain=example.com")
    print(f"  GET /api/status?domain=example.com")
    print(f"  GET /api/results?domain=example.com")
    print(f"  GET /api/settings")
    print(f"  POST /api/settings")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
