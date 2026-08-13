"""Tech & marketing stack detection from HTML, headers, scripts."""
from __future__ import annotations

import re
from typing import Any

from site_recon.utils import evidence_fact

STACK_PATTERNS = {
    "cms_framework": {
        "WordPress": [r"/wp-content/", r"/wp-includes/", r"wp-json"],
        "Shopify": [r"myshopify", r"cdn\.shopify", r"shopify\.com"],
        "Wix": [r"wix\.com", r"static\.wix"],
        "Webflow": [r"webflow\.com", r"data-wf-"],
        "Squarespace": [r"squarespace\.com", r"static1\.squarespace"],
        "Next.js": [r"/_next/", r"__NEXT_DATA__"],
        "Framer": [r"framer\.com", r"framerusercontent"],
        "Webnode": [r"webnode\.com"],
        "React": [r"react", r"data-reactroot", r"data-reactid"],
        "Vue": [r"vue\.js", r"__VUE__"],
        "Lovable": [r"lovable", r"gpteng\.co"],
        "Vite": [r"/assets/", r"modulepreload"],
    },
    "analytics": {
        "Google Analytics 4": [r"gtag", r"GA4", r"google-analytics\.com/g"],
        "Google Tag Manager": [r"googletagmanager\.com/gtm"],
        "Plausible": [r"plausible\.io/js"],
        "Matomo": [r"matomo", r"piwik"],
        "Hotjar": [r"hotjar", r"hj\.js"],
        "Microsoft Clarity": [r"clarity\.ms"],
        "Flock": [r"flock\.js", r"~flock"],
    },
    "ad_pixels": {
        "Meta Pixel": [r"facebook\.com/tr", r"fbq\("],
        "TikTok Pixel": [r"tiktok\.com/tr", r"ttq\("],
        "LinkedIn Insight": [r"linkedin\.com/insight"],
        "Google Ads": [r"googleadservices", r"aw\("],
    },
    "crm_chat": {
        "HubSpot": [r"js\.hubspot\.com", r"hubspot"],
        "Intercom": [r"intercom\.io", r"intercomSettings"],
        "Crisp": [r"crisp\.chat", r"CRISP_"],
        "Tawk.to": [r"tawk\.to", r"Tawk_API"],
    },
    "email": {
        "Mailchimp": [r"mailchimp", r"mcjs"],
        "Klaviyo": [r"klaviyo", r"klaviyo\.com"],
        "ConvertKit": [r"convertkit\.com"],
        "Brevo": [r"brevo", r"sendinblue"],
    },
    "payments": {
        "Stripe": [r"stripe\.com", r"Stripe\("],
        "Paddle": [r"paddle\.com"],
        "Gumroad": [r"gumroad\.com"],
        "LemonSqueezy": [r"lemonsqueezy\.com"],
    },
    "cdn_fonts": {
        "Google Fonts": [r"fonts\.googleapis"],
        "Cloudflare": [r"cloudflare\.com", r"cdnjs\.cloudflare"],
        "jsDelivr": [r"jsdelivr\.net"],
        "Bootstrap": [r"bootstrapcdn"],
    },
}


def collect_tech_stack(homepage_html: str, headers: dict[str, str]) -> dict[str, Any]:
    text = homepage_html
    detected: dict[str, list[str]] = {}
    for category, tools in STACK_PATTERNS.items():
        found = []
        for tool, patterns in tools.items():
            if any(re.search(p, text, re.I) for p in patterns):
                found.append(tool)
            # also check headers
            for hval in headers.values():
                if isinstance(hval, str) and any(re.search(p, hval, re.I) for p in patterns):
                    if tool not in found:
                        found.append(tool)
        detected[category] = found

    # locale
    lang_match = re.search(r'<html[^>]+lang=["\']([^"\']+)["\']', text, re.I)
    hreflang = re.findall(r'<link[^>]+hreflang=["\']([^"\']+)["\']', text, re.I)
    detected["locale"] = {
        "html_lang": lang_match.group(1) if lang_match else None,
        "hreflang": hreflang,
    }
    return evidence_fact(detected, "homepage", "regex_detection")
