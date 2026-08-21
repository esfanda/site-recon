# Site Recon

A local agent that reads a website the way a marketing engineer does, then documents it.

You give it a URL. It collects evidence on your machine and shows a dashboard: what this site is, what the business is, how it works, how serious it looks, and how much you can trust it.

It does not host your scans on the internet.

Vibe-code builder fingerprints (Lovable, Bolt, v0, …) are an extra signal. They are not the point.

## Quick start

You need [Python 3.11+](https://www.python.org/downloads/) first. On the
installer's first screen, tick **Add python.exe to PATH**.

**Windows, no terminal needed:** download this repo (green **Code** button →
**Download ZIP**), unzip it, then:

1. Double-click **`install.cmd`** and wait. It installs everything, once.
2. Double-click **`start.cmd`**. The dashboard opens in your browser.

**Any platform, from a terminal:**

```bash
git clone https://github.com/esfanda/site-recon.git
cd site-recon
pip install -r requirements.txt
playwright install chromium
python dashboard/api.py 8080
```

Open [http://localhost:8080](http://localhost:8080).

There is also a capped **public demo mode** for a hosted try-without-install link:
`python dashboard/api.py 8080 --public-demo`. That mode is not how you run the
tool yourself. See `docs/(C) Hosted Demo Spec.md`.

### The API key

Evidence collection needs no key. The business read does. In the dashboard open
**API key** and follow the step-by-step guide inside it. A free Gemini key takes
about a minute and needs no credit card.

The key is saved to `config/secrets.yaml` on your own machine and is gitignored.
It is never uploaded anywhere. You can also set `GEMINI_API_KEY` or
`DEEPSEEK_API_KEY` in the environment instead.

Without a key the tool still runs and still fills the Identity, Tech Stack,
Health, Traction and Vibe Code tabs. Only the business analysis stays empty.

PageSpeed scores need a **separate** free Google key, because anonymous PageSpeed
requests have a 0/day quota. Get one from
[Google's PageSpeed docs](https://developers.google.com/speed/docs/insights/v5/get-started),
then paste it in the PageSpeed box under **API key**. Without it PageSpeed is
skipped and says so, rather than showing a silent blank.

### Languages

Interface and written analysis both come in English, Persian, Turkish and Arabic.
Switch language in the top right. Each language's analysis is stored separately,
so switching never overwrites one you already ran. Reports download as Markdown
or raw JSON from the buttons next to the verdict.

## What you get

- Identity: RDAP, DNS, TLS, Wayback
- Tech stack: CMS, analytics, pixels, payments
- Traction proxies: Tranco, HN, Reddit, Trustpilot
- Technical health: PageSpeed, on-page, broken links
- Optional LLM layer: what the business claims, how it works, fit verdict, outreach draft
- Extra: vibe-code builder fingerprint (Lovable, Bolt, v0, …) plus a craft / leftover checklist

Fingerprint rule, when that extra layer runs: zero signals means no guess. One strong independent class means likely. Two or more classes plus one strong signal means confirmed. Vite or Supabase alone does not name a builder.

The verdict ships with its reasoning: which builders were checked, what turned up instead, and the blind spot no fingerprint can cover. Editors like Cursor or Claude Code leave no public marker and any builder's output can be moved to ordinary hosting, so "no fingerprint" means "none of the builders checked", never "not AI-built".

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
