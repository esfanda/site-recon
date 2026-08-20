"""Public-demo caps, client IP, and retention cleanup.

Nothing here talks to collectors or the LLM. A refused scan must never reach
those. The SQLite write uses an exclusive lock so two concurrent requests
cannot both sneak under the cap.
"""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from site_recon.config import DEMO_LIMITS_PATH, DEMO_ROOT, REPO_URL, load_yaml

KEEP_NAMES = {"usage.sqlite", "usage.sqlite-journal", "usage.sqlite-wal", "usage.sqlite-shm"}


def load_demo_limits() -> dict[str, Any]:
    path = Path(os.environ.get("SITE_RECON_DEMO_LIMITS", str(DEMO_LIMITS_PATH)))
    data: dict[str, Any] = {}
    if path.exists():
        data = load_yaml(path) or {}
    return {
        "global_daily_cap": int(data.get("global_daily_cap", 20)),
        "per_ip_daily_cap": int(data.get("per_ip_daily_cap", 2)),
        "retention_hours": float(data.get("retention_hours", 48)),
    }


def cap_message() -> str:
    return (
        "Today's free demo scans are used up. Come back tomorrow, or run it "
        f"yourself for free: {REPO_URL}"
    )


def usage_db_path() -> Path:
    override = os.environ.get("SITE_RECON_DEMO_DB")
    if override:
        return Path(override)
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    return DEMO_ROOT / "usage.sqlite"


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def client_ip(headers: Any, client_addr: tuple[str, int] | None) -> str:
    """Prefer Cloudflare's connecting IP. Origin should listen on localhost only."""
    cf = ""
    xff = ""
    if headers is not None:
        cf = (headers.get("CF-Connecting-IP") or headers.get("Cf-Connecting-IP") or "").strip()
        xff = (headers.get("X-Forwarded-For") or "").strip()
    if cf:
        return cf.split(",")[0].strip()
    if xff:
        return xff.split(",")[0].strip()
    if client_addr:
        return client_addr[0]
    return "unknown"


def _connect() -> sqlite3.Connection:
    path = usage_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            ip TEXT NOT NULL,
            domain TEXT,
            ts REAL NOT NULL
        )"""
    )
    return conn


def check_and_record_scan(ip: str, domain: str) -> tuple[bool, str | None]:
    """Atomically refuse or accept. On refuse, nothing is recorded."""
    limits = load_demo_limits()
    day = utc_day()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        global_count = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE day = ?", (day,)
        ).fetchone()[0]
        if global_count >= limits["global_daily_cap"]:
            conn.execute("COMMIT")
            return False, "global"
        ip_count = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE day = ? AND ip = ?", (day, ip)
        ).fetchone()[0]
        if ip_count >= limits["per_ip_daily_cap"]:
            conn.execute("COMMIT")
            return False, "per_ip"
        conn.execute(
            "INSERT INTO scans (day, ip, domain, ts) VALUES (?, ?, ?, ?)",
            (day, ip, domain, time.time()),
        )
        conn.execute("COMMIT")
        return True, None
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def ip_scan_count(ip: str) -> int:
    day = utc_day()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE day = ? AND ip = ?", (day, ip)
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def global_scan_count() -> int:
    day = utc_day()
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM scans WHERE day = ?", (day,)).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def cleanup_demo_data(now: float | None = None) -> list[Path]:
    """Delete files under demo_data older than the retention window."""
    limits = load_demo_limits()
    max_age = limits["retention_hours"] * 3600
    stamp = time.time() if now is None else now
    root = DEMO_ROOT
    if not root.exists():
        return []
    removed: list[Path] = []
    for path in sorted(root.rglob("*"), reverse=True):
        if path.name in KEEP_NAMES:
            continue
        if path.is_dir():
            try:
                next(path.iterdir())
            except StopIteration:
                path.rmdir()
                removed.append(path)
            except OSError:
                pass
            continue
        try:
            age = stamp - path.stat().st_mtime
        except OSError:
            continue
        if age > max_age:
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                pass
    return removed


def strip_personal_sections(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    if not analysis:
        return analysis
    out = dict(analysis)
    out.pop("fit_verdict", None)
    out.pop("collab_brief", None)
    out.pop("outreach", None)
    return out
