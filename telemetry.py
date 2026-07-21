# telemetry.py
"""
Analyst telemetry and override feedback loop — MECE classification.

Captures analyst overrides with structured dropdown categories,
attributable to reason codes, with optional free-text only for
EDGE_CASE or additional detail.

Storage: JSONL file (append-only).
Production: Would migrate to a proper database.
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

TELEMETRY_FILE = "telemetry.jsonl"

# ==================== MECE OVERRIDE CATEGORIES ====================
# Mutually Exclusive, Collectively Exhaustive
# Analyst picks ONE primary category from dropdown.
# Optional free-text for additional detail only.

OVERRIDE_CATEGORIES = {
    "LLM_OVERCONFIDENT": {
        "label": "LLM was overconfident in weak evidence",
        "description": "LLM marked requirement as satisfied/partial but evidence does not actually meet the scheme rule",
        "example": "LLM said delivery proof exists, but tracking number is invalid"
    },
    "LLM_MISSED_EVIDENCE": {
        "label": "LLM missed evidence that exists",
        "description": "Evidence was in the documents but LLM marked it missing",
        "example": "Proof of delivery was on page 3, LLM said not found"
    },
    "LLM_MISREAD_DOCUMENT": {
        "label": "LLM misread or misinterpreted a document",
        "description": "LLM cited wrong page, wrong date, or misunderstood content",
        "example": "LLM said invoice was for £50 but it's actually £500"
    },
    "LLM_IGNORED_IMPOSSIBILITY": {
        "label": "LLM ignored a structural impossibility",
        "description": "LLM suggested requesting evidence that cannot be obtained retroactively",
        "example": "LLM said 'get 3DS proof' but 3DS was not attempted"
    },
    "ANALYST_MORE_CONSERVATIVE": {
        "label": "I am more conservative than the LLM",
        "description": "Evidence technically meets requirements but analyst judges risk too high",
        "example": "Evidence is thin; I'd rather accept liability than lose at arbitration"
    },
    "ANALYST_MORE_AGGRESSIVE": {
        "label": "I am more aggressive than the LLM",
        "description": "Analyst believes case is defensible despite LLM's caution",
        "example": "LLM said request more evidence but I think we have enough"
    },
    "RULE_AMBIGUITY": {
        "label": "Genuine ambiguity in scheme rules",
        "description": "Reason code requirements are unclear for this specific scenario",
        "example": "Digital goods with no shipping — does 'delivery address' requirement apply?"
    },
    "EDGE_CASE": {
        "label": "Other / edge case (describe below)",
        "description": "Does not fit any category above — free text required",
        "example": "Merchant provided evidence in an unexpected format"
    },
    "ANALYST_AGREEMENT": {
        "label": "Analyst agreed with LLM recommendation",
        "description": "No override — analyst accepted the AI recommendation as-is",
        "example": "Analyst clicked Agree — Represent"
    },
    "ADMIN_CORRECTION": {
        "label": "Admin corrected analyst decision",
        "description": "Admin override of a previously recorded analyst decision",
        "example": "Admin changed Accept Liability to Represent after review"
    }
}


def get_override_categories():
    """Return MECE categories for UI dropdown."""
    return {k: v["label"] for k, v in OVERRIDE_CATEGORIES.items()}


def log_override(
    case_id: str,
    reason_code: str,
    llm_recommendation: str,
    analyst_override: str,
    override_category: str,      # ← MECE dropdown choice (required)
    override_detail: str = "",    # ← Optional free-text detail
    analyst_id: str = "anonymous",
    confidence_at_override: int = None,
    provider_used: str = None,     # ← Which LLM made the original rec
    evidence_assessment_snapshot: list = None
):
    """
    Log an analyst override with MECE classification.

    Args:
        override_category: One of OVERRIDE_CATEGORIES keys (required dropdown)
        override_detail: Optional free-text elaboration
        provider_used: Which LLM provider generated the overridden recommendation
    """
    if override_category not in OVERRIDE_CATEGORIES:
        raise ValueError(f"Invalid category: {override_category}. Must be one of: {list(OVERRIDE_CATEGORIES.keys())}")

    # EDGE_CASE requires detail
    if override_category == "EDGE_CASE" and not override_detail.strip():
        raise ValueError("EDGE_CASE requires override_detail to be provided")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "case_id": case_id,
        "reason_code": reason_code,
        "llm_recommendation": llm_recommendation,
        "analyst_override": analyst_override,
        "override_category": override_category,
        "override_category_label": OVERRIDE_CATEGORIES[override_category]["label"],
        "override_detail": override_detail,
        "analyst_id": analyst_id,
        "confidence_at_override": confidence_at_override,
        "provider_used": provider_used,  # ← Critical for LLM attribution
        "evidence_assessment_snapshot": evidence_assessment_snapshot or [],
    }

    with open(TELEMETRY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def overwrite_decision(
    case_id: str,
    new_choice: str,
    admin_id: str = "admin",
    reason: str = ""
):
    """
    Log an admin overwrite of a previously recorded analyst decision.

    Retrieves the case history to preserve the original LLM recommendation
    and reason code, then appends a new ADMIN_CORRECTION entry to the
    telemetry log. Used by the admin panel in app.py when an admin
    overrides a resolved case.

    Args:
        case_id: The case being overwritten.
        new_choice: The admin's new decision (e.g. "represent").
        admin_id: Identifier of the admin performing the overwrite.
        reason: Free-text explanation for the correction.

    Raises:
        ValueError: If no previous decisions exist for the case.
    """
    history = get_case_history(case_id)
    if not history:
        raise ValueError(f"No previous decisions found for case {case_id}")

    # Use the most recent entry to preserve LLM recommendation and metadata
    latest = history[-1]

    # Find the previous analyst decision (most recent non-admin entry)
    # to include context about what is being overwritten
    previous = None
    for entry in reversed(history):
        if entry["override_category"] != "ADMIN_CORRECTION":
            previous = entry
            break
    if previous is None:
        previous = latest

    detail = (
        f"Admin ({admin_id}) overwritten previous decision "
        f"'{previous['analyst_override']}' with '{new_choice}'. "
        f"Reason: {reason}"
    )

    return log_override(
        case_id=case_id,
        reason_code=latest["reason_code"],
        llm_recommendation=latest.get("llm_recommendation", "unknown"),
        analyst_override=new_choice,
        override_category="ADMIN_CORRECTION",
        override_detail=detail,
        analyst_id=admin_id,
        confidence_at_override=latest.get("confidence_at_override"),
        provider_used=latest.get("provider_used", "unknown"),
        evidence_assessment_snapshot=latest.get("evidence_assessment_snapshot", [])
    )


def get_reason_code_stats(reason_code: str) -> Dict:
    """Get aggregated override statistics for a specific reason code.
    Uses ONLY the latest decision per case (handles admin overwrites)."""
    if not os.path.exists(TELEMETRY_FILE):
        return {"total_cases": 0, "override_rate": 0, "by_provider": {}, "common_categories": []}

    # Read all entries
    all_entries = []
    with open(TELEMETRY_FILE, "r") as f:
        for line in f:
            all_entries.append(json.loads(line.strip()))

    # Filter to reason code
    rc_entries = [e for e in all_entries if e["reason_code"] == reason_code]

    # Get latest entry per case (handles overwrites)
    latest_by_case = {}
    for e in rc_entries:
        cid = e["case_id"]
        if cid not in latest_by_case or e["timestamp"] > latest_by_case[cid]["timestamp"]:
            latest_by_case[cid] = e

    entries = list(latest_by_case.values())
    total = len(entries)

    # Overrides = decisions that differ from LLM rec (excluding agreements and admin corrections for rate calc)
    overrides = [e for e in entries if e["override_category"] not in ("NO_OVERRIDE", "ANALYST_AGREEMENT", "ADMIN_CORRECTION")]
    override_rate = len(overrides) / total if total > 0 else 0

    # Admin corrections on this reason code
    admin_corrections = [e for e in entries if e["override_category"] == "ADMIN_CORRECTION"]

    # Break down by LLM provider
    by_provider = {}
    for e in overrides:
        provider = e.get("provider_used", "unknown")
        if provider not in by_provider:
            by_provider[provider] = {"count": 0, "categories": {}}
        by_provider[provider]["count"] += 1
        cat = e["override_category"]
        by_provider[provider]["categories"][cat] = by_provider[provider]["categories"].get(cat, 0) + 1

    # Most common categories across all providers
    category_counts = {}
    for e in overrides:
        cat = e["override_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    common_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_cases": total,
        "override_rate": round(override_rate, 3),
        "override_count": len(overrides),
        "admin_correction_count": len(admin_corrections),
        "by_provider": by_provider,
        "common_categories": common_categories,
        "recent_details": [e["override_detail"] for e in overrides if e["override_detail"]][-5:]
    }


def get_provider_performance(provider: str) -> Dict:
    """
    Get performance metrics for a specific LLM provider.
    Use this to compare providers after N cases mature.
    """
    if not os.path.exists(TELEMETRY_FILE):
        return {"total_cases": 0, "override_rate": 0, "top_categories": []}

    entries = []
    with open(TELEMETRY_FILE, "r") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry.get("provider_used") == provider:
                entries.append(entry)

    overrides = [e for e in entries if e["llm_recommendation"] != e["analyst_override"]]

    category_counts = {}
    for e in overrides:
        cat = e["override_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "provider": provider,
        "total_cases": len(entries),
        "override_count": len(overrides),
        "override_rate": len(overrides) / len(entries) if entries else 0,
        "top_categories": sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    }


def get_prompt_addendum(reason_code: str) -> str:
    """
    Generate a prompt addendum based on historical override data.
    Now includes provider-specific warnings if one LLM underperforms.
    """
    stats = get_reason_code_stats(reason_code)

    if stats["total_cases"] < 3:
        return ""

    addendum_parts = []

    if stats["override_rate"] > 0.3:
        addendum_parts.append(
            f"HISTORICAL NOTE: Analysts have overridden {stats['override_rate']*100:.0f}% of "
            f"recommendations for this reason code. Be extra cautious."
        )

    # Provider-specific warnings
    for provider, data in stats.get("by_provider", {}).items():
        provider_override_rate = data["count"] / stats["total_cases"]
        if provider_override_rate > 0.4:
            addendum_parts.append(
                f"PROVIDER WARNING: {provider.upper()} has a {provider_override_rate*100:.0f}% "
                f"override rate on this reason code. Double-check all claims."
            )

    # Category-specific guidance
    for category, count in stats["common_categories"]:
        if category == "LLM_OVERCONFIDENT":
            addendum_parts.append(
                "COMMON PITFALL: Past analyses were overridden for being overconfident "
                "in evidence that sounded authoritative but lacked substantive proof. "
                "Verify every claim against the actual requirements."
            )
        elif category == "LLM_MISSED_EVIDENCE":
            addendum_parts.append(
                "COMMON PITFALL: Past analyses missed evidence buried in multi-page documents. "
                "Check every page carefully, especially tables and appendices."
            )
        elif category == "LLM_IGNORED_IMPOSSIBILITY":
            addendum_parts.append(
                "COMMON PITFALL: Past analyses ignored structural impossibilities "
                "(e.g., AVS mismatch cannot be fixed retroactively). Flag these explicitly."
            )

    if stats.get("recent_details"):
        addendum_parts.append(
            f"RECENT ANALYST FEEDBACK: {stats['recent_details'][-1][:120]}"
        )

    return "\n\n" + "\n".join(addendum_parts) if addendum_parts else ""


def get_all_telemetry_summary() -> Dict:
    """Get summary across all reason codes and providers.
    Uses ONLY latest decision per case (handles admin overwrites)."""
    if not os.path.exists(TELEMETRY_FILE):
        return {"total_cases": 0, "total_overrides": 0, "reason_code_breakdown": {}, "provider_breakdown": {}}

    all_entries = []
    with open(TELEMETRY_FILE, "r") as f:
        for line in f:
            all_entries.append(json.loads(line.strip()))

    # Get latest entry per case
    latest_by_case = {}
    for e in all_entries:
        cid = e["case_id"]
        if cid not in latest_by_case or e["timestamp"] > latest_by_case[cid]["timestamp"]:
            latest_by_case[cid] = e

    latest_entries = list(latest_by_case.values())

    # Analyst overrides (excluding agreements and admin corrections)
    analyst_overrides = [e for e in latest_entries if e["llm_recommendation"] != e["analyst_override"] and e["override_category"] not in ("ANALYST_AGREEMENT", "ADMIN_CORRECTION")]

    # Admin corrections
    admin_corrections = [e for e in latest_entries if e["override_category"] == "ADMIN_CORRECTION"]

    # By reason code (analyst overrides only for learning signal)
    by_reason = {}
    for e in analyst_overrides:
        rc = e["reason_code"]
        if rc not in by_reason:
            by_reason[rc] = []
        by_reason[rc].append(e)

    # By provider (all decisions, with override counts)
    by_provider = {}
    for e in latest_entries:
        provider = e.get("provider_used", "unknown")
        if provider not in by_provider:
            by_provider[provider] = {"total": 0, "overrides": 0, "admin_corrections": 0}
        by_provider[provider]["total"] += 1
        if e["llm_recommendation"] != e["analyst_override"] and e["override_category"] not in ("ANALYST_AGREEMENT", "ADMIN_CORRECTION"):
            by_provider[provider]["overrides"] += 1
        if e["override_category"] == "ADMIN_CORRECTION":
            by_provider[provider]["admin_corrections"] += 1

    return {
        "total_cases": len(latest_entries),
        "total_overrides": len(analyst_overrides),
        "total_admin_corrections": len(admin_corrections),
        "overall_override_rate": len(analyst_overrides) / len(latest_entries) if latest_entries else 0,
        "reason_code_breakdown": {
            rc: {
                "override_count": len(entries),
                "top_category": max(
                    set(e["override_category"] for e in entries),
                    key=lambda c: sum(1 for e in entries if e["override_category"] == c)
                ) if entries else None
            }
            for rc, entries in by_reason.items()
        },
        "provider_breakdown": {
            provider: {
                "total_cases": data["total"],
                "overrides": data["overrides"],
                "admin_corrections": data["admin_corrections"],
                "override_rate": data["overrides"] / data["total"] if data["total"] > 0 else 0
            }
            for provider, data in by_provider.items()
        }
    }


# --- UI Integration ---

def record_analyst_decision(
    case_data: dict,
    analysis_result: dict,
    analyst_choice: str,
    override_category: str,
    override_detail: str = "",
    analyst_id: str = "anonymous"
):
    """Record an analyst's final decision."""
    return log_override(
        case_id=case_data["case_id"],
        reason_code=case_data["reason_code"],
        llm_recommendation=analysis_result.get("recommendation", "unknown"),
        analyst_override=analyst_choice,
        override_category=override_category,
        override_detail=override_detail,
        analyst_id=analyst_id,
        confidence_at_override=analysis_result.get("confidence_score"),
        provider_used=analysis_result.get("provider_used", "unknown"),
        evidence_assessment_snapshot=analysis_result.get("evidence_assessment", [])
    )


def get_case_history(case_id: str) -> List[Dict]:
    """Get full decision history for a case (including overwrites)."""
    if not os.path.exists(TELEMETRY_FILE):
        return []

    entries = []
    with open(TELEMETRY_FILE, "r") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry["case_id"] == case_id:
                entries.append(entry)

    return entries