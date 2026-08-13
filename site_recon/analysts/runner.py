"""Run all analyst stages against collected evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from site_recon.analysts.schemas import (
    BUSINESS_TEARDOWN_SCHEMA,
    CLAIM_AUDIT_SCHEMA,
    COLLAB_BRIEF_SCHEMA,
    FIT_VERDICT_SCHEMA,
    OUTREACH_SCHEMA,
    PAIN_POINTS_SCHEMA,
)
from site_recon.config import DATA_DIR, REPORTS_DIR
from site_recon.llm import call_llm


def _evidence_text(evidence: dict[str, Any]) -> str:
    """Trim evidence to a digestible text for LLM."""
    lines = []
    for section, data in evidence.items():
        if section == "meta":
            continue
        lines.append(f"## {section}")
        val = data.get("value") if isinstance(data, dict) else data
        if val is None:
            lines.append(f"ERROR: {data.get('error', 'unknown')}")
        else:
            lines.append(json.dumps(val, ensure_ascii=False, indent=2)[:4000])
        lines.append("")
    return "\n".join(lines)


def run_analysts(evidence: dict[str, Any], profile: str, relationship: str = "cold") -> dict[str, Any]:
    ev_text = _evidence_text(evidence)
    results: dict[str, Any] = {}

    try:
        # A. Claim Audit
        results["claim_audit"] = call_llm(
            system_prompt="You are a claim auditor. Extract the value proposition and grade every factual claim.",
            user_prompt=f"Evidence:\n{ev_text}\n\nProfile:\n{profile}",
            schema=CLAIM_AUDIT_SCHEMA,
        )

        # B. Business Teardown
        results["business_teardown"] = call_llm(
            system_prompt="You are a business analyst. Describe the business model, funnel, and what is worth stealing.",
            user_prompt=f"Evidence:\n{ev_text}",
            schema=BUSINESS_TEARDOWN_SCHEMA,
        )

        # C. Pain Points
        results["pain_points"] = call_llm(
            system_prompt="You are a marketing consultant. List concrete pain points with severity and business impact. ONLY use evidence provided.",
            user_prompt=f"Evidence:\n{ev_text}\n\nProfile services:\n{profile}",
            schema=PAIN_POINTS_SCHEMA,
        )

        # D. Fit & Verdict
        results["fit_verdict"] = call_llm(
            system_prompt=f"You are a fit analyst. Score the site against the operator profile. Return ONE label. relationship={relationship}",
            user_prompt=f"Evidence:\n{ev_text}\n\nProfile:\n{profile}",
            schema=FIT_VERDICT_SCHEMA,
        )

        # E/F. Outreach or Collab Brief
        label = results["fit_verdict"].get("label", "SKIP")
        if relationship == "friend":
            results["collab_brief"] = call_llm(
                system_prompt="You are giving honest feedback to a friend about their site. No sales language. Write in first person.",
                user_prompt=f"Evidence:\n{ev_text}\n\nProfile:\n{profile}\n\nPain points:\n{json.dumps(results['pain_points'], ensure_ascii=False)}",
                schema=COLLAB_BRIEF_SCHEMA,
            )
        elif label == "LEAD" and results["fit_verdict"].get("fit_score", 0) >= 60:
            site_lang = evidence.get("tech_stack", {}).get("value", {}).get("locale", {}).get("html_lang", "en")
            results["outreach"] = call_llm(
                system_prompt=f"Draft a cold outreach message in language '{site_lang}'. Open with ONE specific observation. No generic compliments. Max 120 words.",
                user_prompt=f"Evidence:\n{ev_text}\n\nPain points:\n{json.dumps(results['pain_points'], ensure_ascii=False)}",
                schema=OUTREACH_SCHEMA,
            )
    except RuntimeError as exc:
        # Fallback: generate placeholder analysis when LLM fails
        results = _mock_analysis(evidence, relationship, str(exc))

    # Write analysts output
    domain = evidence["meta"]["domain"]
    out_path = DATA_DIR / domain / "analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def _mock_analysis(evidence: dict[str, Any], relationship: str, error_msg: str) -> dict[str, Any]:
    """Generate placeholder analysis when LLM is unavailable."""
    domain = evidence["meta"]["domain"]
    health = evidence.get("health", {})
    on_page = health.get("on_page", {}).get("value", {}) if isinstance(health.get("on_page"), dict) else {}
    pagespeed = health.get("pagespeed", {}).get("value", {}) if isinstance(health.get("pagespeed"), dict) else {}
    tech = evidence.get("tech_stack", {}).get("value", {}) if isinstance(evidence.get("tech_stack"), dict) else {}
    
    # Build pain points from evidence
    pain_points = []
    if on_page:
        if not on_page.get("has_viewport"):
            pain_points.append({"problem": "Missing viewport meta tag (poor mobile experience)", "evidence_key": "health.on_page", "severity": 3, "business_impact": "Mobile users get broken layout", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "1 hour"})
        if on_page.get("images_without_alt", 0) > 0:
            pain_points.append({"problem": f"{on_page['images_without_alt']} images without alt text", "evidence_key": "health.on_page", "severity": 2, "business_impact": "Accessibility and SEO penalty", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "30 min"})
        if not on_page.get("meta_description"):
            pain_points.append({"problem": "Missing meta description", "evidence_key": "health.on_page", "severity": 3, "business_impact": "Lower click-through rate from search", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "15 min"})
        if not on_page.get("has_favicon"):
            pain_points.append({"problem": "Missing favicon", "evidence_key": "health.on_page", "severity": 1, "business_impact": "Unprofessional appearance in browser tabs", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "15 min"})
        if not on_page.get("h1"):
            pain_points.append({"problem": "Missing H1 heading", "evidence_key": "health.on_page", "severity": 3, "business_impact": "Poor SEO structure and user orientation", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "30 min"})
        if not on_page.get("has_og"):
            pain_points.append({"problem": "Missing Open Graph tags", "evidence_key": "health.on_page", "severity": 2, "business_impact": "Poor social sharing previews", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "30 min"})
        if not on_page.get("has_schema"):
            pain_points.append({"problem": "Missing structured data (schema.org)", "evidence_key": "health.on_page", "severity": 2, "business_impact": "Missed rich snippet opportunities in search", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "1 hour"})
    
    if pagespeed and pagespeed.get("scores"):
        perf = pagespeed["scores"].get("performance")
        if perf is not None and perf < 0.5:
            pain_points.append({"problem": f"Low PageSpeed performance score ({perf})", "evidence_key": "health.pagespeed", "severity": 4, "business_impact": "High bounce rate from slow loading", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "2-4 hours"})
        seo = pagespeed["scores"].get("seo")
        if seo is not None and seo < 0.5:
            pain_points.append({"problem": f"Low PageSpeed SEO score ({seo})", "evidence_key": "health.pagespeed", "severity": 3, "business_impact": "Poor search engine visibility", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "2-4 hours"})
    
    if tech:
        if not tech.get("analytics"):
            pain_points.append({"problem": "No analytics detected", "evidence_key": "tech_stack", "severity": 4, "business_impact": "Cannot measure marketing ROI", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "1 hour"})
        if not tech.get("crm_chat"):
            pain_points.append({"problem": "No live chat or CRM integration detected", "evidence_key": "tech_stack", "severity": 2, "business_impact": "Missed real-time engagement opportunities", "fixable_by_operator": True, "matching_service": "Digital marketing", "estimated_effort": "1-2 hours"})
    
    # Crawl issues
    crawl = health.get("crawl", {}).get("value", {}) if isinstance(health.get("crawl"), dict) else {}
    if crawl:
        broken = crawl.get("broken", [])
        if broken:
            pain_points.append({"problem": f"{len(broken)} broken links found", "evidence_key": "health.crawl", "severity": 3, "business_impact": "Poor user experience and SEO penalty", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "1 hour"})
        redirects = crawl.get("redirects", [])
        if redirects:
            pain_points.append({"problem": f"{len(redirects)} redirect chains found", "evidence_key": "health.crawl", "severity": 2, "business_impact": "Slower page loads and diluted link equity", "fixable_by_operator": True, "matching_service": "Website build/redesign", "estimated_effort": "1-2 hours"})
    
    # Determine label based on evidence
    label = "LEARN"
    fit_score = 30
    if relationship == "friend":
        label = "COLLAB"
        fit_score = 50
    
    result = {
        "claim_audit": {
            "value_proposition": f"[LLM unavailable: {error_msg[:80]}]",
            "claims": [],
            "testimonials": [],
            "red_flags": []
        },
        "business_teardown": {
            "business_model": "[LLM unavailable - analysis requires LLM]",
            "revenue_mechanics": "",
            "pricing_tiers": "",
            "target_segment": "",
            "positioning": "",
            "main_hook": "",
            "funnel": "",
            "copywriting_quality": "",
            "estimated_size": "",
            "worth_stealing": ["[Run with working LLM for full analysis]"]
        },
        "pain_points": {
            "pain_points": pain_points
        },
        "fit_verdict": {
            "label": label,
            "fit_score": fit_score,
            "confidence": "low",
            "reasoning": f"LLM analysis unavailable: {error_msg[:100]}. Label defaulted based on relationship mode.",
            "next_action": "Re-run with working DeepSeek API key for full analysis"
        }
    }
    
    if relationship == "friend":
        result["collab_brief"] = {
            "honest_feedback": [f"[LLM unavailable - could not generate feedback: {error_msg[:80]}]"],
            "collaboration_angles": []
        }
    
    return result
