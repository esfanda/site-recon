"""CLI entry point for Site Recon."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from site_recon.analysts.runner import run_analysts
from site_recon.collectors.__main__ import run_all as run_collectors
from site_recon.config import DATA_DIR, REPORTS_DIR, ensure_dirs, load_profile, load_scoring, load_sources
from site_recon.render.index import update_index
from site_recon.render.report import render_report

console = Console()


def cmd_run(args: argparse.Namespace) -> int:
    ensure_dirs()
    url = args.url
    if not url.startswith("http"):
        url = "https://" + url

    try:
        profile = load_profile()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    if getattr(args, "llm_only", False):
        domain = args.url.replace("https://", "").replace("http://", "").strip("/")
        ev_path = DATA_DIR / domain / "evidence.json"
        if not ev_path.exists():
            console.print(f"[red]No evidence for {domain}. Run a full collect first.[/red]")
            return 1
        with open(ev_path, "r", encoding="utf-8") as f:
            evidence = json.load(f)
        console.print(f"[bold cyan]Re-running analysts for {domain}...[/bold cyan]")
        if args.no_llm:
            analysis = {}
        else:
            analysis = run_analysts(evidence, profile, relationship=args.relationship)
        report_path = render_report(domain, evidence, analysis, status="new")
        console.print(f"[green]Report saved: {report_path}[/green]")
        return 0

    # Collect
    console.print(f"[bold cyan]Collecting evidence for {url}...[/bold cyan]")
    evidence = run_collectors(url, use_playwright=not args.fast, fast=args.fast)
    domain = evidence["meta"]["domain"]

    # Analyze
    if args.no_llm:
        console.print("[yellow]--no-llm: skipping analysts[/yellow]")
        analysis = {}
    else:
        console.print("[bold cyan]Running analysts...[/bold cyan]")
        analysis = run_analysts(evidence, profile, relationship=args.relationship)

    # Render
    console.print("[bold cyan]Rendering report...[/bold cyan]")
    report_path = render_report(domain, evidence, analysis, status="new")
    console.print(f"[green]Report saved: {report_path}[/green]")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    ensure_dirs()
    path = Path(args.file)
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        return 1
    urls = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    for url in urls:
        console.print(f"[bold]--- {url} ---[/bold]")
        ret = cmd_run(argparse.Namespace(url=url, no_llm=args.no_llm, fast=args.fast, relationship="cold"))
        if ret != 0:
            console.print(f"[red]Failed for {url}[/red]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    domain = args.domain
    ev_path = DATA_DIR / domain / "evidence.json"
    an_path = DATA_DIR / domain / "analysis.json"
    if not ev_path.exists():
        console.print(f"[red]No evidence found for {domain}[/red]")
        return 1
    with open(ev_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)
    analysis = {}
    if an_path.exists():
        with open(an_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)
    report_path = render_report(domain, evidence, analysis)
    console.print(f"[green]Report re-rendered: {report_path}[/green]")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    # Rebuild INDEX.md from all existing reports
    rows = []
    for p in REPORTS_DIR.glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        domain = p.stem
        analysis = data.get("analysis", {})
        meta = data.get("evidence", {}).get("meta", {})
        pain_points = analysis.get("pain_points", {}).get("pain_points", [])
        top_pain = pain_points[0]["problem"][:60] if pain_points else "-"
        rows.append({
            "domain": domain,
            "date": meta.get("collected_at", "")[:10],
            "label": analysis.get("fit_verdict", {}).get("label", "?"),
            "fit_score": analysis.get("fit_verdict", {}).get("fit_score", "?"),
            "top_pain": top_pain,
            "next_action": analysis.get("fit_verdict", {}).get("next_action", "?"),
            "status": "new",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    from jinja2 import Template
    tmpl = Template("""# Site Recon Index

| Domain | Date Analyzed | Label | Fit Score | Top Pain Point | Next Action | Status |
|--------|---------------|-------|-----------|----------------|-------------|--------|
{% for row in rows %}
| {{ row.domain }} | {{ row.date }} | {{ row.label }} | {{ row.fit_score }} | {{ row.top_pain }} | {{ row.next_action }} | {{ row.status }} |
{% endfor %}
""")
    (REPORTS_DIR / "INDEX.md").write_text(tmpl.render(rows=rows), encoding="utf-8")
    console.print("[green]INDEX.md rebuilt.[/green]")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    # Update status in INDEX.md
    domain = args.domain
    state = args.state
    index_path = REPORTS_DIR / "INDEX.md"
    if not index_path.exists():
        console.print("[red]INDEX.md not found[/red]")
        return 1
    text = index_path.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("|") and domain in line and "Domain" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 8:
                parts[-2] = state
                line = "|" + "|".join(parts[1:-1]) + "|"
        lines.append(line)
    index_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Status for {domain} updated to {state}.[/green]")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    console.print("[yellow]diff: not yet implemented[/yellow]")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recon", description="Site Recon CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Analyze a single URL")
    p_run.add_argument("url")
    p_run.add_argument("--no-llm", action="store_true", help="Skip LLM analysts")
    p_run.add_argument("--fast", action="store_true", help="Skip Playwright/PageSpeed/social")
    p_run.add_argument("--relationship", choices=["friend", "cold"], default="cold")
    p_run.add_argument("--llm-only", action="store_true", help="Reuse cached evidence; run analysts only")
    p_run.add_argument("--lang", choices=["fa", "en"], default=None)
    p_run.set_defaults(func=cmd_run)

    p_batch = sub.add_parser("batch", help="Analyze URLs from a file")
    p_batch.add_argument("file")
    p_batch.add_argument("--no-llm", action="store_true")
    p_batch.add_argument("--fast", action="store_true")
    p_batch.set_defaults(func=cmd_batch)

    p_report = sub.add_parser("report", help="Re-render report from cached evidence")
    p_report.add_argument("domain")
    p_report.set_defaults(func=cmd_report)

    p_index = sub.add_parser("index", help="Rebuild INDEX.md")
    p_index.set_defaults(func=cmd_index)

    p_status = sub.add_parser("status", help="Update outreach status")
    p_status.add_argument("domain")
    p_status.add_argument("state", choices=["new", "contacted", "replied", "dead"])
    p_status.set_defaults(func=cmd_status)

    p_diff = sub.add_parser("diff", help="Show what changed since last run")
    p_diff.add_argument("domain")
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
