# BUILD SPEC — Site Recon: Capped Public Demo

See phases 1–5 below. Implementation lives on branch `cursor/hosted-demo-f2b2`.

## 5. Decisions

- **Tunnel type:** Quick Tunnel first (`deploy/site-recon-demo-tunnel.service`). Named tunnel / stable subdomain is optional after validation.
- **systemd units:** Shipped in-repo at `deploy/site-recon-demo.service` and `deploy/site-recon-demo-tunnel.service`. On the Pi: `/etc/systemd/system/`. WorkingDirectory `/opt/site-recon`, User `erfan`. Demo key in `/opt/site-recon/config/demo.env` (`chmod 600`). Dashboard binds `127.0.0.1` only; cloudflared is the public listener.
- **Caps (defaults):** 20 scans/day global, 2/day/IP, 48-hour retention. SQLite at `demo_data/usage.sqlite` with `BEGIN IMMEDIATE`. UTC day boundary. Client IP: `CF-Connecting-IP`, then `X-Forwarded-For`, then socket.
- **Mode flag:** `--public-demo` on `dashboard/api.py` and `cli run`. Storage `demo_data/` (gitignored). Key from `SITE_RECON_DEMO_KEY` or `config/demo_secrets.yaml` only — never reads personal `config/profile.md`, `data/`, or `reports/`.
- **FIT/COLLAB:** omitted from LLM schema, stripped from JSON, hidden in UI, omitted from Markdown report.
- **Deploy from PC (home LAN):** double-click `deploy.cmd`, or:
  ```powershell
  cd d:\GitHub\site-recon
  git checkout cursor/hosted-demo-f2b2
  deploy.cmd
  ```
- **Deploy on Pi directly** (SSH into Pi):
  ```bash
  export SITE_RECON_DEMO_KEY='your-key'
  curl -fsSL https://raw.githubusercontent.com/esfanda/site-recon/cursor/hosted-demo-f2b2/deploy/pi_pull_and_bootstrap.sh | bash
  ```
- **Get public URL after deploy:**
  ```bash
  ssh erfan@192.168.1.105 "sudo journalctl -u site-recon-demo-tunnel -n 30 --no-pager | grep trycloudflare"
  ```

## Phases (summary)

1. **Public demo mode** — `--public-demo`, isolated `demo_data/`, no FIT/COLLAB, server-side key only.
2. **Hard usage cap** — global + per-IP daily limits; refuse before any collector/LLM.
3. **Auto-delete** — cleanup of `demo_data/` older than retention window.
4. **Cloudflare Tunnel on Pi** — systemd services, quick tunnel first.
5. **Acceptance** — external URL, real scan, cap block, reboot persistence, retention check.

Self-tests: `scripts/test_demo_mode.py`, `scripts/test_demo_caps.py`, `scripts/test_demo_cleanup.py`.
