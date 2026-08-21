#!/usr/bin/env bash
# Bootstrap the capped public demo on home-pi.
set -euo pipefail

APP=/opt/site-recon
VENV="$APP/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
PORT=8080

echo "==> Ensure app dir"
sudo mkdir -p "$APP"
sudo chown -R erfan:erfan "$APP"
cd "$APP"

echo "==> Python venv + deps"
if [[ ! -x "$PY" ]]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip python3-venv python3-full
  python3 -m venv "$VENV"
fi
"$PIP" install --upgrade pip
"$PIP" install -r requirements.txt
"$PY" -m playwright install chromium
"$PY" -m playwright install-deps chromium 2>/dev/null || true

echo "==> cloudflared"
if ! command -v cloudflared >/dev/null 2>&1; then
  tmp=$(mktemp)
  curl -fsSL -o "$tmp" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
  sudo install -m 755 "$tmp" /usr/local/bin/cloudflared
  rm -f "$tmp"
fi
cloudflared --version

if [[ ! -f config/demo.env ]]; then
  echo "Missing config/demo.env — copy deploy/demo.env.example and set SITE_RECON_DEMO_KEY" >&2
  exit 1
fi
chmod 600 config/demo.env

echo "==> systemd"
sudo cp deploy/site-recon-demo.service /etc/systemd/system/
# Prefer Named Tunnel when config exists; otherwise keep Quick Tunnel reachable.
if [[ -f /home/erfan/.cloudflared/config.yml ]]; then
  sudo cp deploy/site-recon-demo-tunnel.service /etc/systemd/system/
  echo "Using Named Tunnel unit (config.yml present)"
else
  sudo cp deploy/site-recon-demo-tunnel-quick.service /etc/systemd/system/site-recon-demo-tunnel.service
  echo "Using Quick Tunnel fallback (no ~/.cloudflared/config.yml yet)"
fi
sudo systemctl daemon-reload
sudo systemctl enable site-recon-demo site-recon-demo-tunnel
sudo systemctl restart site-recon-demo
sleep 2
sudo systemctl restart site-recon-demo-tunnel
sleep 5

systemctl is-active site-recon-demo
systemctl is-active site-recon-demo-tunnel
curl -sf "http://127.0.0.1:${PORT}/api/mode" | head -c 200 || true
echo
if [[ -f /home/erfan/.cloudflared/config.yml ]]; then
  echo "Named hostname target: site-recon.erfandigital.com"
else
  sudo journalctl -u site-recon-demo-tunnel -n 30 --no-pager | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true
fi
