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
    HYGIENE_SCHEMA,
    OUTREACH_SCHEMA,
    PAIN_POINTS_SCHEMA,
)
from site_recon.config import DATA_DIR, REPORTS_DIR
from site_recon.llm import RateLimitError, call_llm


# --- What counts as a finding ----------------------------------------------
# The old prompt was one sentence ("You are a marketer reading a site recon").
# With no definition of a finding, the model reached for the only checklist
# facts in the evidence and reported "missing H1" as a marketing gap. That
# sentence can be written about any site on earth without looking at it, which
# is exactly what makes it worthless as feedback.

SYSTEM_PROMPT = """You are a marketing engineer reading a site recon. You have the page a
visitor actually sees: visible_text, headings, cta_texts, auth_providers,
empty_sections, pricing and funnel signals. Read those first. The technical
checks are background, not the story.

WHAT A MARKETING GAP IS
A marketing gap costs THIS business visitors, signups, trust, or revenue, and
you can only name it after understanding what this business is trying to do.

THE TEST, apply it to every gap before you write it down:
Could this exact sentence be written about a random website you have never
opened? If yes, it is not a marketing gap. Delete it.

NEVER put these in pain_points. They belong in hygiene, always:
missing or duplicate H1, missing or short meta description, missing alt text,
missing favicon, missing schema.org or structured data, missing Open Graph or
Twitter cards, no sitemap.xml, no robots directives, no analytics detected,
no cookie banner, no live chat, minification, generic "improve page speed"
with no measured number.
Those are real, and they are also true of thousands of sites. Listing them as
the headline finding tells the owner you did not read their site.

WHAT TO LOOK FOR INSTEAD
- A section that promises content and is empty. See empty_sections. On a
  community or marketplace site an empty section is the product looking dead.
- Supply concentration: most listings coming from one or two accounts.
- The signup wall: how many auth providers, and does the audience named in the
  copy actually use them.
- A prototype or builder badge still visible in production. See
  visible_builder_badge. It tells every visitor this is not a real product.
- A promise in the hero that nothing further down the page delivers.
- The gap between the stated audience and the audience the copy addresses.
- Where the money is supposed to come from, and whether the page makes that
  path possible at all.
- Whether search engines can reach the content the business depends on, stated
  with the specific pages at stake, not as "SEO is missing".

RULES FOR EACH GAP
- specific_observation must quote or name something literally present on this
  site: a heading, a button label, a count, a line of copy. If you cannot fill
  it from the evidence, you do not have a finding.
- business_impact names who loses what. Not "bad for SEO". Say which visitor
  does what instead, or which revenue does not arrive.
- severity is about money and trust, not about tidiness.
- At most 6 gaps, hardest-hitting first. Four real ones beat six padded ones.
- Never invent evidence. If you did not see it, say not_verified in hygiene
  and leave it out of pain_points.

Fill every section. Use only the evidence."""


# Output language for the human-readable parts of the analysis. Enum fields
# (labels, grades, categories, statuses) always stay English because the UI
# maps them to its own translations.
LANG_NAMES = {
    "en": "English",
    "fa": "Persian (Farsi)",
    "tr": "Turkish",
    "ar": "Arabic",
}


def analysis_path(domain: str, lang: str = "en") -> Path:
    """Where one language's analysis lives.

    Kept per language so switching the UI language does not overwrite a
    previous run, and so an already-paid-for analysis is never thrown away.
    """
    return DATA_DIR / domain / f"analysis.{lang}.json"


def _language_note(lang: str) -> str:
    if lang == "en":
        return ""
    name = LANG_NAMES.get(lang, "English")
    note = (
        "\n\nWRITE THE OUTPUT IN " + name.upper() + ". "
        "Every human-readable string you produce must be in " + name + ": "
        "value_proposition, positioning, hook, target_segment, business_model, "
        "revenue_mechanics, pricing_tiers, funnel, copywriting_quality, "
        "estimated_size, worth_stealing, problem, specific_observation, "
        "business_impact, matching_service, estimated_effort, reasoning, "
        "next_action, honest_feedback, and every hygiene check and note. "
        "Keep these values in English exactly as the schema defines them, they "
        "are enums the interface translates itself: label, grade, category, "
        "status, credibility, confidence, evidence_key. "
        "Keep product names, brand names, technical terms and quoted text from "
        "the site in their original form, do not translate them."
    )
    if lang == "fa":
        note += (
            " Persian has no em dash. Never use the character U+2014 in Persian "
            "text. Use a comma, a colon, parentheses, or split the sentence."
        )
    return note


def _system_prompt(relationship: str, has_image: bool, lang: str = "en") -> str:
    vision_note = (
        "\n\nA screenshot of the rendered homepage is attached as an image. "
        "Actually look at it, zoomed into each card and section, before writing "
        "business_teardown or pain_points. Specifically check: do any badges or "
        "labels overlap card borders or other text, does any text get clipped "
        "or overflow its container, are card heights inconsistent in a way that "
        "looks broken rather than intentional, is anything misaligned. "
        "If you find any of that, it IS a pain point (category trust or "
        "positioning, since broken cards read as an unfinished product) - add it "
        "with a specific_observation naming which card and what is wrong, do not "
        "leave it out just because it is a visual issue. "
        "Never write 'clean', 'polished', 'minimalist', or 'professional design' "
        "about layout anywhere in this response, in worth_stealing included, "
        "unless you are also naming one specific element that earns it. A vague "
        "compliment about visual quality is worse than saying nothing."
        if has_image
        else "\n\nNo screenshot was available for this run. You have text content "
        "only. Do NOT make any claim about visual design, layout, polish, "
        "spacing, or how 'clean' the UI is. You have not seen the page."
    )
    return SYSTEM_PROMPT + vision_note + _language_note(lang) + "\n\nrelationship=" + relationship


# Deterministic backstop for the ban list above.
_HYGIENE_PATTERNS = (
    "h1", "meta description", "alt text", "alt attribute", "favicon",
    "schema.org", "structured data", "open graph", "og tag", "twitter card",
    "sitemap", "robots.txt", "analytics", "cookie notice", "cookie banner",
    "live chat", "minif", "viewport",
)


def _split_hygiene(pain_points: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Move checklist items out of the headline findings.

    Runs even when the model complies, because one boilerplate item at the top
    of the list is enough to make the whole report read as automated."""
    kept: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    for point in pain_points.get("pain_points") or []:
        text = (point.get("problem", "") + " " + point.get("specific_observation", "")).lower()
        if any(pat in text for pat in _HYGIENE_PATTERNS):
            demoted.append(
                {
                    "check": point.get("problem", ""),
                    "status": "fail",
                    "note": point.get("business_impact", ""),
                }
            )
        else:
            kept.append(point)
    kept.sort(key=lambda p: p.get("severity", 0), reverse=True)
    return {"pain_points": kept}, demoted


def _trim_value(val: Any) -> Any:
    if not isinstance(val, dict):
        return val
    out: dict[str, Any] = {}
    for key, item in val.items():
        if key == "headers":
            continue
        if key == "html_snippet" and isinstance(item, str):
            out[key] = item[:4000]
            continue
        out[key] = item
    return out


def _section_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    if "value" in data or "error" in data:
        if data.get("value") is None:
            return {"error": data.get("error", "unknown")}
        return _trim_value(data["value"])
    compact: dict[str, Any] = {}
    for key, item in data.items():
        if isinstance(item, dict) and ("value" in item or "error" in item):
            if item.get("value") is None:
                compact[key] = {"error": item.get("error", "unknown")}
            else:
                compact[key] = _trim_value(item["value"])
        else:
            compact[key] = item
    return compact


def _evidence_text(evidence: dict[str, Any]) -> str:
    """Trim evidence to a digestible text for LLM."""
    lines = []
    for section, data in evidence.items():
        if section == "meta":
            continue
        lines.append(f"## {section}")
        payload = _section_payload(data)
        blob = json.dumps(payload, ensure_ascii=False, indent=2)
        lines.append(blob[:8000])
        lines.append("")
    return "\n".join(lines)


def _combined_schema(relationship: str) -> dict[str, Any]:
    properties = {
        "claim_audit": CLAIM_AUDIT_SCHEMA,
        "business_teardown": BUSINESS_TEARDOWN_SCHEMA,
        "pain_points": PAIN_POINTS_SCHEMA,
        "hygiene": HYGIENE_SCHEMA,
        "fit_verdict": FIT_VERDICT_SCHEMA,
    }
    required = ["claim_audit", "business_teardown", "pain_points", "hygiene", "fit_verdict"]
    if relationship == "friend":
        properties["collab_brief"] = COLLAB_BRIEF_SCHEMA
        required.append("collab_brief")
    else:
        properties["outreach"] = OUTREACH_SCHEMA
    return {"type": "object", "properties": properties, "required": required}


def run_analysts(evidence: dict[str, Any], profile: str, relationship: str = "cold", lang: str = "en") -> dict[str, Any]:
    ev_text = _evidence_text(evidence)
    results: dict[str, Any] = {}

    screenshot_path = evidence.get("pages", {}).get("screenshot", {}).get("value")
    if screenshot_path and not Path(screenshot_path).is_file():
        screenshot_path = None

    try:
        parsed = call_llm(
            system_prompt=_system_prompt(relationship, has_image=bool(screenshot_path), lang=lang),
            user_prompt=f"Evidence:\n{ev_text}\n\nOperator profile:\n{profile}",
            schema=_combined_schema(relationship),
            max_tokens=8192,
            image_path=screenshot_path,
        )
        results["claim_audit"] = parsed.get("claim_audit") or {}
        results["business_teardown"] = parsed.get("business_teardown") or {}
        results["pain_points"] = parsed.get("pain_points") or {"pain_points": []}
        results["hygiene"] = parsed.get("hygiene") or {"items": []}
        results["fit_verdict"] = parsed.get("fit_verdict") or {}
        # Safety net: the model still slips checklist items in sometimes.
        results["pain_points"], demoted = _split_hygiene(results["pain_points"])
        results["hygiene"]["items"].extend(demoted)
        if relationship == "friend":
            results["collab_brief"] = parsed.get("collab_brief") or {
                "honest_feedback": [],
                "collaboration_angles": [],
            }
        elif parsed.get("outreach"):
            results["outreach"] = parsed["outreach"]
    except RateLimitError:
        results = _mock_analysis(evidence, relationship, reason="rate_limit")
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not configured" in msg or "bad_key" in msg:
            reason = "no_key"
        elif "no_credit" in msg:
            reason = "no_credit"
        elif "unavailable" in msg:
            reason = "unavailable"
        else:
            reason = "error"
        results = _mock_analysis(evidence, relationship, reason=reason)

    # Write analysts output
    domain = evidence["meta"]["domain"]
    out_path = analysis_path(domain, lang)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def _mock_analysis(evidence: dict[str, Any], relationship: str, reason: str = "error") -> dict[str, Any]:
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
    
    result = {
        "llm_status": {"ok": False, "reason": reason},
        "claim_audit": {
            "value_proposition": "",
            "claims": [],
            "testimonials": [],
            "red_flags": []
        },
        "business_teardown": {
            "business_model": "",
            "revenue_mechanics": "",
            "pricing_tiers": "",
            "target_segment": "",
            "positioning": "",
            "main_hook": "",
            "funnel": "",
            "copywriting_quality": "",
            "estimated_size": "",
            "worth_stealing": []
        },
        "pain_points": {
            "pain_points": []
        },
        "hygiene": {
            "items": [
                {"check": p["problem"], "status": "fail", "note": p.get("business_impact", "")}
                for p in pain_points
            ]
        },
        "fit_verdict": {
            "label": "PARTIAL",
            "fit_score": None,
            "confidence": "low",
            "reasoning": "",
            "next_action": ""
        }
    }
    
    if relationship == "friend":
        result["collab_brief"] = {
            "honest_feedback": [],
            "collaboration_angles": []
        }
    
    return result
