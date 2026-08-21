#!/usr/bin/env python3
"""Simple HTTP API server for Site Recon Dashboard."""

import json
import os
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DASHBOARD_DIR = Path(__file__).parent
PROJECT_DIR = DASHBOARD_DIR.parent
PUBLIC_DEMO = "--public-demo" in sys.argv
if PUBLIC_DEMO:
    os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from site_recon.collectors.health import probe_pagespeed_key  # noqa: E402
from site_recon.collectors.vibe_code import score_vibe_code  # noqa: E402
from site_recon.config import (  # noqa: E402
    REPO_URL,
    data_dir,
    get_deepseek_key,
    get_demo_gemini_key,
    get_gemini_key,
    get_pagespeed_key,
    is_public_demo,
    load_sources,
    reports_dir,
    save_secrets,
    settings_public,
)
from site_recon.demo import (  # noqa: E402
    cap_message,
    check_and_record_scan,
    cleanup_demo_data,
    client_ip,
    global_scan_count,
    ip_daily_cap,
    ip_scan_count,
    public_demo_limits,
    strip_personal_sections,
)
from site_recon.llm import probe_key  # noqa: E402

RUN_TIMEOUT_SECONDS = 480

jobs = {}
SUBPROCESS_STARTS = 0
_run_lock = __import__("threading").Lock()


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/run":
            self.handle_run(query)
            return
        if path == "/api/status":
            self.handle_status(query)
            return
        if path == "/api/results":
            self.handle_results(query)
            return
        if path == "/api/domains":
            self.handle_domains()
            return
        if path == "/api/report":
            self.handle_report(query)
            return
        if path == "/api/settings":
            self.handle_settings_get()
            return
        if path == "/api/mode":
            self.handle_mode()
            return
        if path == "/api/demo-usage":
            self.handle_demo_usage()
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if is_public_demo() and parsed.path in ("/api/settings", "/api/pagespeed-key"):
            self.send_json({"error": "Not available on the public demo"}, 404)
            return
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
        if is_public_demo():
            cleanup_demo_data()

        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return

        lang = (query.get("lang", ["en"])[0] or "en").strip().lower()
        if lang not in ("en", "fa", "tr", "ar"):
            lang = "en"

        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        if is_public_demo():
            ip = client_ip(self.headers, self.client_address)
            ok, cap = check_and_record_scan(ip, domain)
            if not ok:
                print(f"demo: blocked cap={cap} ip={ip} domain={domain}", flush=True)
                self.send_json({
                    "error": cap_message(),
                    "capped": True,
                    "cap": cap,
                }, 429)
                return

        if domain in jobs and jobs[domain]["status"] == "running":
            self.send_json({"status": "running", "domain": domain, "message": "Recon already in progress"})
            return

        store = data_dir()
        ev_path = store / domain / "evidence.json"
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

        if is_public_demo() and os.environ.get("SITE_RECON_DEMO_SKIP_RUN") == "1":
            jobs[domain]["status"] = "done"
            jobs[domain]["ended"] = time.time()
            self.send_json({"status": "started", "domain": domain, "message": "Recon started (skip-run test mode)"})
            return

        def run_recon():
            global SUBPROCESS_STARTS
            try:
                cmd = [
                    sys.executable, "-m", "site_recon.cli", "run", f"https://{domain}",
                    "--relationship", "friend", "--lang", lang,
                ]
                if llm_only:
                    cmd.append("--llm-only")
                if is_public_demo():
                    cmd.append("--public-demo")
                env = os.environ.copy()
                if is_public_demo():
                    env["SITE_RECON_PUBLIC_DEMO"] = "1"
                    demo_key = get_demo_gemini_key()
                    if demo_key:
                        env["SITE_RECON_DEMO_KEY"] = demo_key
                    env.pop("GEMINI_API_KEY", None)
                    env.pop("DEEPSEEK_API_KEY", None)
                with _run_lock:
                    SUBPROCESS_STARTS += 1
                print(f"demo: subprocess_start domain={domain}" if is_public_demo() else f"recon start {domain}", flush=True)
                result = subprocess.run(
                    cmd,
                    cwd=str(PROJECT_DIR),
                    capture_output=True,
                    text=True,
                    # A heavy site on a Raspberry Pi ran past five minutes and
                    # the visitor got nothing at all. A slow answer beats none.
                    timeout=RUN_TIMEOUT_SECONDS,
                    env=env,
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
                jobs[domain]["error"] = f"Timeout after {RUN_TIMEOUT_SECONDS // 60} minutes"
            except Exception as exc:
                jobs[domain]["status"] = "error"
                jobs[domain]["error"] = str(exc)
            finally:
                jobs[domain]["ended"] = time.time()

        import threading
        threading.Thread(target=run_recon, daemon=True).start()
        self.send_json({"status": "started", "domain": domain, "message": "Recon started"})

    def handle_status(self, query):
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return
        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        if domain not in jobs:
            evidence_file = data_dir() / domain / "evidence.json"
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

        lang = (query.get("lang", ["en"])[0] or "en").strip().lower()
        if lang not in ("en", "fa", "tr", "ar"):
            lang = "en"

        store = data_dir()
        evidence_file = store / domain / "evidence.json"
        analysis_file = store / domain / f"analysis.{lang}.json"
        analysis_lang = lang
        if not analysis_file.exists():
            legacy = store / domain / "analysis.json"
            english = store / domain / "analysis.en.json"
            if lang == "en" and legacy.exists():
                analysis_file, analysis_lang = legacy, "en"
            elif english.exists():
                analysis_file, analysis_lang = english, "en"
            elif legacy.exists():
                analysis_file, analysis_lang = legacy, "en"

        result = {
            "domain": domain,
            "evidence": None,
            "analysis": None,
            "lang": lang,
            "analysis_lang": analysis_lang,
        }

        if evidence_file.exists():
            try:
                with open(evidence_file, "r", encoding="utf-8") as f:
                    result["evidence"] = json.load(f)
            except Exception as exc:
                result["evidence_error"] = str(exc)

        if analysis_file.exists():
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    analysis = json.load(f)
                if is_public_demo():
                    analysis = strip_personal_sections(analysis)
                result["analysis"] = analysis
            except Exception as exc:
                result["analysis_error"] = str(exc)

        if result["evidence"] is None and result["analysis"] is None:
            self.send_json({"error": f"No data found for {domain}. Run recon first."}, 404)
            return

        if result["evidence"]:
            result["vibe_code"] = score_vibe_code(result["evidence"])

        self.send_json(result)

    def handle_report(self, query):
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self.send_json({"error": "Domain required"}, 400)
            return
        domain = domain.replace("https://", "").replace("http://", "").strip("/")
        if "/" in domain or "\\" in domain or ".." in domain:
            self.send_json({"error": "Invalid domain"}, 400)
            return

        fmt = (query.get("format", ["md"])[0] or "md").strip().lower()
        if fmt not in ("md", "json"):
            fmt = "md"
        lang = (query.get("lang", ["en"])[0] or "en").strip().lower()
        if lang not in ("en", "fa", "tr", "ar"):
            lang = "en"

        suffix = "" if lang == "en" else f".{lang}"
        path = reports_dir() / f"{domain}{suffix}.{fmt}"
        if not path.exists() and lang != "en":
            path = reports_dir() / f"{domain}.{fmt}"
        if not path.exists():
            self.send_json({"error": f"No {fmt} report for {domain}. Run the analysis first."}, 404)
            return

        try:
            payload = path.read_bytes()
        except OSError as exc:
            self.send_json({"error": str(exc)}, 500)
            return

        ctype = "text/markdown; charset=utf-8" if fmt == "md" else "application/json; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_domains(self):
        if is_public_demo():
            self.send_json({"domains": []})
            return
        domains = []
        store = data_dir()
        if store.exists():
            for d in store.iterdir():
                if d.is_dir() and (d / "evidence.json").exists():
                    domains.append(d.name)
        self.send_json({"domains": domains})

    def handle_settings_get(self):
        if is_public_demo():
            self.send_json({"error": "Not available on the public demo"}, 404)
            return
        self.send_json(settings_public())

    def handle_mode(self):
        limits = public_demo_limits() if is_public_demo() else {}
        self.send_json({
            "public_demo": is_public_demo(),
            "repo_url": REPO_URL,
            "limits": limits,
        })

    def handle_demo_usage(self):
        if not is_public_demo():
            self.send_json({"error": "Not available"}, 404)
            return
        ip = client_ip(self.headers, self.client_address)
        used = ip_scan_count(ip)
        self.send_json({
            "used": used,
            "limit": ip_daily_cap(ip),
            "global_used": global_scan_count(),
            "global_limit": public_demo_limits()["global_daily_cap"],
        })

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


def run_server(port=8080, public_demo=False):
    if public_demo:
        os.environ["SITE_RECON_PUBLIC_DEMO"] = "1"
    ThreadingHTTPServer.allow_reuse_address = True
    bind = "127.0.0.1" if is_public_demo() else ""
    server = ThreadingHTTPServer((bind, port), APIHandler)
    mode = "public demo" if is_public_demo() else "local"
    print(f"Site Recon Dashboard API running ({mode}) at http://localhost:{port}", flush=True)
    if is_public_demo():
        print("Public demo: FIT/COLLAB off, data in demo_data/, caps on.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "--public-demo"]
    port = int(argv[0]) if argv else 8080
    run_server(port, public_demo=PUBLIC_DEMO)
