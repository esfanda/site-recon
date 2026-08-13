# Site Recon

Deep, evidence-based website analysis CLI tool. Turns a URL into a decision in under 5 minutes.

## What it does

Site Recon analyzes a website and produces a structured report covering:

- **Identity & Age**: Domain registration, DNS, TLS certificate, Wayback Machine history
- **Tech Stack**: CMS, analytics, ad pixels, CRM, payments, fonts/CDNs
- **Traction Proxies**: Tranco rank, Hacker News mentions, Reddit discussions, Trustpilot reviews
- **Technical Health**: PageSpeed scores, on-page SEO checks, broken links, crawl issues
- **Business Analysis**: Claim audit, business teardown, pain points & opportunities
- **Fit Verdict**: LEAD / TOOL / MODEL / COMPETITOR / LEARN / SKIP / COLLAB
- **Outreach Draft**: Cold message grounded in specific, verifiable observations (when label is LEAD)
- **Friend Mode**: Honest feedback & collaboration angles instead of cold outreach (when `--relationship friend`)

## Architecture

Three separate layers:

1. **Layer A — Collectors** (deterministic Python, no LLM): Fetch facts, write to `data/<domain>/evidence.json`
2. **Layer B — Analysts** (LLM, DeepSeek): Read evidence, produce structured JSON analysis
3. **Layer C — Render** (Jinja2): Generate `reports/<domain>.md` and update `reports/INDEX.md`

## Installation

```bash
git clone <repo>
cd site-recon
pip install -r requirements.txt
playwright install chromium
```

## Configuration

1. Copy the example profile and fill it in:
```bash
cp config/profile.example.md config/profile.md
```

2. Add your DeepSeek API key (optional — tool falls back to mock analysis without it):
```bash
export DEEPSEEK_API_KEY=your-key-here
```
   Or edit `config/sources.yaml` and set `apis.deepseek.api_key`.

## Usage

```bash
# Analyze a single URL
python -m site_recon.cli run <url>

# Fast mode (skip Playwright, PageSpeed, social checks)
python -m site_recon.cli run <url> --fast

# No LLM (raw evidence report only)
python -m site_recon.cli run <url> --no-llm

# Friend / warm-relationship mode
python -m site_recon.cli run <url> --relationship friend

# Batch analysis
python -m site_recon.cli run batch urls.txt

# Re-render report from cached evidence
python -m site_recon.cli report <domain>

# Rebuild INDEX.md
python -m site_recon.cli index

# Update outreach status
python -m site_recon.cli status <domain> contacted
```

## Data Sources

| Source | Cost | Key Required | Notes |
|--------|------|--------------|-------|
| RDAP (rdap.org) | Free | No | Domain registration data |
| Cloudflare DNS | Free | No | DNS over HTTPS |
| SSL Certificate | Free | No | TLS info from socket |
| Wayback Machine | Free | No | Historical snapshots |
| PageSpeed Insights | Free | No | Google API, rate limited |
| Tranco List | Free | No | Downloaded once, offline lookup |
| Hacker News Search | Free | No | Algolia API |
| Reddit Search | Free | No | Public search API |
| Trustpilot | Free | No | Public page scraping |
| DuckDuckGo | Free | No | Fragile, wrapped in try/except |
| DeepSeek LLM | Paid | Yes | Only paid dependency |

## Acceptance Tests

Run these to verify the tool works:

```bash
# Test 1: learnwhywebuy.com — should produce real tech stack, label should be LEARN/TOOL/MODEL (not LEAD)
python -m site_recon.cli run https://learnwhywebuy.com

# Test 2: menapark.com with --relationship friend — should produce COLLAB label, Feedback & Collaboration Angles section
python -m site_recon.cli run https://menapark.com --relationship friend

# Test 3: Any small business site — should complete without crashing, missing data renders as "not verified"
python -m site_recon.cli run https://example-small-business.com --fast
```

## Privacy

- `config/profile.md` contains personal/financial details and is gitignored by default
- `data/` and `reports/` are gitignored — they may contain others' site data
- Never commit real evidence or reports to version control

## Cost Control

- All LLM outputs are cached keyed by evidence hash (TTL: 7 days)
- Per-site token cap configurable in `config/scoring.yaml`
- `--no-llm` mode produces raw evidence without any API calls
- `--fast` mode skips Playwright, PageSpeed, and social checks

## Anti-Hallucination

- Every LLM response is validated against a JSON schema; retries up to 2 times
- Pain points without an `evidence_key` are stripped, not softened
- No traffic volume numbers are ever output — only proxies actually collected
- OBSERVED vs INFERRED markers distinguish evidence from model judgment

## License

MIT
