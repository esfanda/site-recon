"""JSON schemas for each analyst stage."""
from __future__ import annotations

CLAIM_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "value_proposition": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "grade": {"type": "string", "enum": ["verified", "unsupported", "contradicted"]},
                    "evidence_key": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["claim", "grade", "evidence_key"],
            },
        },
        "testimonials": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "credibility": {"type": "string", "enum": ["strong", "medium", "weak"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["text", "credibility"],
            },
        },
        "red_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "flag": {"type": "string"},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "evidence_key": {"type": "string"},
                },
                "required": ["flag", "severity", "evidence_key"],
            },
        },
    },
    "required": ["value_proposition", "claims", "testimonials", "red_flags"],
}

BUSINESS_TEARDOWN_SCHEMA = {
    "type": "object",
    "properties": {
        "business_model": {"type": "string"},
        "revenue_mechanics": {"type": "string"},
        "pricing_tiers": {"type": "string"},
        "target_segment": {"type": "string"},
        "positioning": {"type": "string"},
        "main_hook": {"type": "string"},
        "funnel": {"type": "string"},
        "copywriting_quality": {"type": "string"},
        "estimated_size": {"type": "string"},
        "worth_stealing": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["business_model", "revenue_mechanics", "target_segment", "positioning", "funnel", "copywriting_quality", "estimated_size", "worth_stealing"],
}

PAIN_POINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "pain_points": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string"},
                    # A literal thing seen on THIS site: quoted copy, a section
                    # name, a button label, a count. Without it a "finding" is
                    # just a checklist item wearing a suit.
                    "specific_observation": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "positioning",
                            "conversion",
                            "trust",
                            "acquisition",
                            "retention",
                            "monetization",
                        ],
                    },
                    "evidence_key": {"type": "string"},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "business_impact": {"type": "string"},
                    "fixable_by_operator": {"type": "boolean"},
                    "matching_service": {"type": "string"},
                    "estimated_effort": {"type": "string"},
                },
                "required": [
                    "problem",
                    "specific_observation",
                    "category",
                    "evidence_key",
                    "severity",
                    "business_impact",
                    "fixable_by_operator",
                ],
            },
        },
    },
    "required": ["pain_points"],
}

# Deterministic on-page checks. Real, worth listing, but true of thousands of
# sites and therefore never a headline finding.
HYGIENE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check": {"type": "string"},
                    "status": {"type": "string", "enum": ["pass", "fail", "not_verified"]},
                    "note": {"type": "string"},
                },
                "required": ["check", "status"],
            },
        },
    },
    "required": ["items"],
}

FIT_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["LEAD", "TOOL", "MODEL", "COMPETITOR", "LEARN", "SKIP", "COLLAB"]},
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string"},
        "next_action": {"type": "string"},
    },
    "required": ["label", "fit_score", "confidence", "reasoning", "next_action"],
}

OUTREACH_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "why_now": {"type": "string"},
    },
    "required": ["message", "why_now"],
}

COLLAB_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "honest_feedback": {
            "type": "array",
            "items": {"type": "string"},
        },
        "collaboration_angles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "gap": {"type": "string"},
                    "operator_service": {"type": "string"},
                    "why_it_fits": {"type": "string"},
                    "suggested_first_step": {"type": "string"},
                },
                "required": ["gap", "operator_service", "why_it_fits", "suggested_first_step"],
            },
        },
    },
    "required": ["honest_feedback", "collaboration_angles"],
}
