# Named Tunnel — site-recon.erfandigital.com

Stable public URL for the Pi demo (instead of changing `*.trycloudflare.com` links).

## Requirements

1. Cloudflare account (free is enough).
2. Domain `erfandigital.com` **DNS managed by Cloudflare** (nameservers must be Cloudflare, not `dns-parking.com` / registrar parking).
3. On the Pi: `cloudflared`, origin cert at `~/.cloudflared/cert.pem`.

## One-time on the Pi

```bash
# Browser login (prints a URL). Leave the process running until cert.pem appears.
cloudflared tunnel login

cloudflared tunnel create site-recon-demo
# Note the tunnel UUID printed / shown by:
cloudflared tunnel list

# Write config (replace UUID):
#   /home/erfan/.cloudflared/config.yml
# Use deploy/cloudflared.config.example.yml as the template.

# Only works if erfandigital.com is a Cloudflare zone:
cloudflared tunnel route dns site-recon-demo site-recon.erfandigital.com

sudo cp /opt/site-recon/deploy/site-recon-demo-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart site-recon-demo-tunnel
sudo systemctl status site-recon-demo-tunnel --no-pager
```

## If the domain is not on Cloudflare yet

1. Add `erfandigital.com` to Cloudflare (Free plan).
2. At the registrar, set nameservers to the two Cloudflare NS values.
3. Wait until the zone is Active.
4. Keep existing records for the portfolio site (`@` / `www` → Vercel or current host).
5. Then run `cloudflared tunnel route dns site-recon-demo site-recon.erfandigital.com`
   (creates CNAME `site-recon` → `<tunnel-id>.cfargotunnel.com`).

Until DNS is on Cloudflare, keep the Quick Tunnel fallback so the demo stays reachable:

```bash
# temporary — URL changes when the unit restarts
sudo sed -i 's|ExecStart=.*|ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080|' \
  /etc/systemd/system/site-recon-demo-tunnel.service
sudo systemctl daemon-reload
sudo systemctl restart site-recon-demo-tunnel
```

## Verify

```bash
curl -sS https://site-recon.erfandigital.com/api/mode
# expect: "public_demo": true
```
