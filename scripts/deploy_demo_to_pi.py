#!/usr/bin/env python3
"""Upload site-recon to home-pi and run deploy/pi_bootstrap.sh."""
from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
HOST = os.environ.get("SITE_RECON_PI_HOST", "192.168.1.105")
USER = os.environ.get("SITE_RECON_PI_USER", "erfan")
PASSWORD = os.environ.get("SITE_RECON_PI_PASSWORD", "HomePi2026")
REMOTE = "/opt/site-recon"
SKIP = {".git", "__pycache__", "demo_data", "data", "reports", ".venv", "venv", "node_modules"}


def should_skip(rel: Path) -> bool:
    if set(rel.parts) & SKIP:
        return True
    if rel.suffix in {".pyc", ".pyo"}:
        return True
    if rel.name in {"secrets.yaml", "demo_secrets.yaml", "demo.env"}:
        return True
    return False


def build_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if should_skip(rel):
                continue
            tar.add(path, arcname=str(rel).replace("\\", "/"))
    return buf.getvalue()


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 900) -> int:
    print(f"$ {cmd}", flush=True)
    _, stdout, _ = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out, end="" if out.endswith("\n") else "\n", flush=True)
    return code


def main() -> int:
    demo_key = os.environ.get("SITE_RECON_DEMO_KEY")
    if not demo_key:
        print("Set SITE_RECON_DEMO_KEY in the environment.", file=sys.stderr)
        return 1

    payload = build_tar()
    print(f"Built tarball: {len(payload) / 1024 / 1024:.1f} MiB", flush=True)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, allow_agent=False, look_for_keys=False)

    sftp = client.open_sftp()
    remote_tar = "/tmp/site-recon-demo.tgz"
    with sftp.file(remote_tar, "wb") as f:
        f.write(payload)
    sftp.close()

    steps = [
        f"sudo mkdir -p {REMOTE} && sudo chown -R {USER}:{USER} {REMOTE}",
        f"tar -xzf {remote_tar} -C {REMOTE}",
        f"rm -f {remote_tar}",
        f"mkdir -p {REMOTE}/config",
        f"printf '%s\\n' 'SITE_RECON_DEMO_KEY={demo_key}' > {REMOTE}/config/demo.env",
        f"chmod 600 {REMOTE}/config/demo.env",
        f"chmod +x {REMOTE}/deploy/pi_bootstrap.sh",
        f"bash {REMOTE}/deploy/pi_bootstrap.sh",
    ]
    for cmd in steps:
        if run(client, cmd) != 0:
            client.close()
            return 1

    _, stdout, _ = client.exec_command(
        "sudo journalctl -u site-recon-demo-tunnel -n 40 --no-pager | grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' | tail -1",
        timeout=60,
    )
    out = stdout.read().decode().strip()
    url = out.splitlines()[-1] if out else ""
    client.close()
    if url:
        print(f"TUNNEL_URL={url}", flush=True)
    else:
        print("WARN: could not read trycloudflare URL", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
