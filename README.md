# Site Recon

A local agent that reads a website the way a marketing engineer does, then documents it.

You give it a URL. It collects evidence on your machine and shows a dashboard: what this site is, what the business is, how it works, how serious it looks, and how much you can trust it.

It does not host your scans on the internet.

Vibe-code builder fingerprints (Lovable, Bolt, v0, …) are an extra signal. They are not the point.

## Quick start

```bash
git clone https://github.com/esfanda/site-recon.git
cd site-recon
pip install -r requirements.txt
playwright install chromium
python dashboard/api.py 8080
```

Open [http://localhost:8080](http://localhost:8080).

Evidence collection does not need an API key. Business analysis does. In the dashboard, open **API key**, pick Gemini or DeepSeek, and paste your own key. It is saved in `config/secrets.yaml` on that machine and is gitignored.

You can also set `GEMINI_API_KEY` or `DEEPSEEK_API_KEY` in the environment.

PageSpeed scores need a separate, free Google API key (https://developers.google.com/speed/docs/insights/v5/get-started) since anonymous PageSpeed requests have a 0/day quota. Set `PAGESPEED_API_KEY` in the environment or `pagespeed_api_key` in `config/secrets.yaml`. Without it, PageSpeed is skipped, not silently empty.

## What you get

- Identity: RDAP, DNS, TLS, Wayback
- Tech stack: CMS, analytics, pixels, payments
- Traction proxies: Tranco, HN, Reddit, Trustpilot
- Technical health: PageSpeed, on-page, broken links
- Optional LLM layer: what the business claims, how it works, fit verdict, outreach draft
- Extra: vibe-code builder fingerprint (Lovable, Bolt, v0, …) plus a craft / leftover checklist

Fingerprint rule, when that extra layer runs: zero signals means no guess. One strong independent class means likely. Two or more classes plus one strong signal means confirmed. Vite or Supabase alone does not name a builder.

## CLI

```bash
python -m site_recon.cli run https://example.com
python -m site_recon.cli run https://example.com --fast
python -m site_recon.cli run https://example.com --no-llm
python -m site_recon.cli run https://example.com --relationship friend
```

Copy `config/profile.example.md` to `config/profile.md` before LLM analysis that needs your positioning.

## Architecture

1. **Collectors** — deterministic Python, no LLM, writes `data/<domain>/evidence.json`
2. **Analysts** — Gemini (or DeepSeek), structured JSON
3. **Render** — Jinja reports in `reports/`

`data/` and `reports/` are gitignored. Do not commit other people's site data.

## Author

Erfan · I help people who build with AI turn the product into a business.

[erfandigital.com](https://erfandigital.com) · [GitHub](https://github.com/esfanda/site-recon)

## License

MIT
