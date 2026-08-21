#!/usr/bin/env bash
# Run ON the Pi when you cannot deploy from a PC (e.g. git clone already there).
# Usage on Pi:
#   export SITE_RECON_DEMO_KEY='your-gemini-key'
#   bash deploy/pi_pull_and_bootstrap.sh
set -euo pipefail

APP=/opt/site-recon
REPO="${SITE_RECON_REPO:-https://github.com/esfanda/site-recon.git}"
BRANCH="${SITE_RECON_BRANCH:-cursor/hosted-demo-f2b2}"

sudo mkdir -p "$APP"
sudo chown -R erfan:erfan "$APP"

if [[ ! -d "$APP/.git" ]]; then
  git clone --branch "$BRANCH" --depth 1 "$REPO" "$APP"
else
  cd "$APP"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

cd "$APP"
if [[ -z "${SITE_RECON_DEMO_KEY:-}" ]]; then
  echo "Set SITE_RECON_DEMO_KEY before running." >&2
  exit 1
fi
mkdir -p config
printf '%s\n' "SITE_RECON_DEMO_KEY=$SITE_RECON_DEMO_KEY" > config/demo.env
chmod 600 config/demo.env
chmod +x deploy/pi_bootstrap.sh
bash deploy/pi_bootstrap.sh
