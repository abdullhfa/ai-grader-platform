"""
Governance Failure Taxonomy v1 — breakdown modes (not grading errors).

Classifies drift events, pilot incidents, and reviewer confusion into
institutional governance failure modes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TAXONOMY_ID = "GOVERNANCE_FAILURE_TAXONOMY_v1"

# Canonical failure modes (frozen for pilot)
FAILURE_MODES: Dict[str, Dict[str, Any]] = {
    "GFM_AUTHORITY_INFLATION": {
        "label_en": "authority_inflation",
        "label_ar": "تضخم السلطة",
        "description_ar": "L1–L3 تُعامل كـ verification أو criterion authority.",
        "examples": ["L3 treated as verification", "executable → Achieved implied"],
        "default_severity": "high",
    },
    "GFM_CONTRADICTION_INVISIBILITY": {
        "label_en": "contradiction_invisibility",
        "label_ar": "إخفاء التعارض",
        "description_ar": "contradictions موجودة لكن غير ظاهرة في flags/replay.",
        "examples": ["replay omits downgrade", "claim_flags empty despite ambiguity"],
        "default_severity": "medium",
    },
    "GFM_SEMANTIC_ESCALATION": {
        "label_en": "semantic_escalation",
        "label_ar": "تصعيد دلالي",
        "description_ar": "لغة أقوى من freeze (confirmed, verified, works).",
        "examples": ["gameplay verified", "criterion confirmed", "مؤكد تماماً"],
        "default_severity": "medium",
    },
    "GFM_REPLAY_INCOMPLETENESS": {
        "label_en": "replay_incompleteness",
        "label_ar": "نقص provenance",
        "description_ar": "authority_replay/graph ناقص رغم وجود governance artifacts.",
        "examples": ["missing replay steps", "no trace graph"],
        "default_severity": "low",
    },
    "GFM_FALSE_CORROBORATION": {
        "label_en": "false_corroboration",
        "label_ar": "تأييد زائف",
        "description_ar": "hints ضعيفة تُعامل كـ strong corroboration.",
        "examples": ["weak hint → strong claim", "single filename = verified"],
        "default_severity": "medium",
    },
    "GFM_MODALITY_DOMINANCE": {
        "label_en": "modality_dominance",
        "label_ar": "هيمنة modality",
        "description_ar": "video/screenshot يتجاوز code/contradiction signals.",
        "examples": ["video overrides code mismatch", "vision narrative authority"],
        "default_severity": "high",
    },
    "GFM_DRIFT_SILENCE": {
        "label_en": "drift_silence",
        "label_ar": "صمت drift",
        "description_ar": "freeze violation بدون detection أو surfacing.",
        "examples": ["L4 auto-assigned undetected", "no drift monitor flag"],
        "default_severity": "critical",
    },
    "GFM_BOUNDARY_OMISSION": {
        "label_en": "boundary_omission",
        "label_ar": "غياب حدود السلطة",
        "description_ar": "coverage/authority notes غائبة عند artifacts حساسة.",
        "examples": ["exe present, no coverage notice"],
        "default_severity": "medium",
    },
    "GFM_REVIEWER_AUTHORITY_CONFUSION": {
        "label_en": "reviewer_authority_confusion",
        "label_ar": "لبس مراجع — سلطة",
        "description_ar": "مراجع بشري يخلط advisory مع verification (pilot manual).",
        "examples": ["reviewer said verified for L2 only"],
        "default_severity": "high",
        "source": "manual_workshop",
    },
    "GFM_TRUST_EROSION": {
        "label_en": "trust_erosion",
        "label_ar": "تآكل ثقة",
        "description_ar": "فقدان ثقة مؤسسية بعد disagreement (pilot manual).",
        "examples": ["AI said so fallback", "replay ignored in review"],
        "default_severity": "high",
        "source": "manual_workshop",
    },
    "GFM_CANONICAL_DRIFT": {
        "label_en": "canonical_drift",
        "label_ar": "انحراف مرجعي",
        "description_ar": "نفس دليل التسليم (grading_hash) → نتائج مؤسسية متباينة.",
        "examples": [
            "identical file P vs D across batches",
            "cache miss → AI variance on M/D criteria",
        ],
        "default_severity": "critical",
        "source": "grading_snapshot_governance",
    },
}

# Drift monitor code → taxonomy mode
_DRIFT_CODE_TO_MODE: Dict[str, str] = {
    "runtime_level_exceeds_freeze_ceiling": "GFM_AUTHORITY_INFLATION",
    "reserved_level_auto_assigned": "GFM_DRIFT_SILENCE",
    "forbidden_claim_drift": "GFM_SEMANTIC_ESCALATION",
    "strong_verification_language": "GFM_SEMANTIC_ESCALATION",
    "confirmed_working": "GFM_SEMANTIC_ESCALATION",
    "definite_achievement_claim": "GFM_SEMANTIC_ESCALATION",
    "certainty_language": "GFM_SEMANTIC_ESCALATION",
    "ar_certainty_language": "GFM_SEMANTIC_ESCALATION",
    "ar_game_works_praise": "GFM_SEMANTIC_ESCALATION",
    "l3_confused_with_verification": "GFM_AUTHORITY_INFLATION",
    "language_drift": "GFM_SEMANTIC_ESCALATION",
    "overall_feedback_drift": "GFM_SEMANTIC_ESCALATION",
    "contradictions_not_in_claim_flags": "GFM_CONTRADICTION_INVISIBILITY",
    "provenance_replay_missing": "GFM_REPLAY_INCOMPLETENESS",
    "replay_ignores_contradiction": "GFM_CONTRADICTION_INVISIBILITY",
    "executable_present_no_coverage_notice": "GFM_BOUNDARY_OMISSION",
}

# Cross-artifact / temporal consistency codes → taxonomy
_CROSS_ARTIFACT_TO_MODE: Dict[str, str] = {
    "modality_divergence_video_platformer_code_puzzle": "GFM_MODALITY_DOMINANCE",
    "vision_engine_mismatch": "GFM_MODALITY_DOMINANCE",
    "video_screenshot_visual_mismatch": "GFM_MODALITY_DOMINANCE",
    "hud_stable_score_unchanged": "GFM_FALSE_CORROBORATION",
    "executable_without_corroborating_artifacts": "GFM_FALSE_CORROBORATION",
}


def classify_drift_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Attach taxonomy classification to a drift monitor signal."""
    code = str(signal.get("code") or "")
    mode_id = _DRIFT_CODE_TO_MODE.get(code, "GFM_SEMANTIC_ESCALATION")
    mode = FAILURE_MODES.get(mode_id, {})
    return {
        **signal,
        "taxonomy_id": TAXONOMY_ID,
        "failure_mode_id": mode_id,
        "failure_mode_en": mode.get("label_en"),
        "failure_mode_ar": mode.get("label_ar"),
    }


def classify_consistency_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Classify temporal/cross-artifact consistency signal."""
    code = str(signal.get("code") or "")
    mode_id = _CROSS_ARTIFACT_TO_MODE.get(code, "GFM_CONTRADICTION_INVISIBILITY")
    if "modality" in code or "divergence" in code or "mismatch" in code:
        mode_id = _CROSS_ARTIFACT_TO_MODE.get(code, "GFM_MODALITY_DOMINANCE")
    mode = FAILURE_MODES.get(mode_id, {})
    return {
        **signal,
        "taxonomy_id": TAXONOMY_ID,
        "failure_mode_id": mode_id,
        "failure_mode_en": mode.get("label_en"),
        "failure_mode_ar": mode.get("label_ar"),
    }


def classify_workshop_incident(
    *,
    incident_type: str,
    notes_ar: str = "",
    submission_id: Optional[int] = None,
    reviewer_confused_l3: bool = False,
    trust_eroded: bool = False,
) -> Dict[str, Any]:
    """Classify manual pilot / workshop incident."""
    mode_id = "GFM_REVIEWER_AUTHORITY_CONFUSION"
    if trust_eroded:
        mode_id = "GFM_TRUST_EROSION"
    elif reviewer_confused_l3:
        mode_id = "GFM_AUTHORITY_INFLATION"
    elif incident_type == "false_corroboration":
        mode_id = "GFM_FALSE_CORROBORATION"
    elif incident_type == "modality_dominance":
        mode_id = "GFM_MODALITY_DOMINANCE"
    elif incident_type == "contradiction_hidden":
        mode_id = "GFM_CONTRADICTION_INVISIBILITY"

    mode = FAILURE_MODES.get(mode_id, {})
    return {
        "taxonomy_id": TAXONOMY_ID,
        "failure_mode_id": mode_id,
        "failure_mode_en": mode.get("label_en"),
        "failure_mode_ar": mode.get("label_ar"),
        "source": "manual_workshop",
        "submission_id": submission_id,
        "incident_type": incident_type,
        "notes_ar": notes_ar,
    }


def aggregate_failure_modes(
    classified_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Count failure modes for cohort observatory."""
    counts: Dict[str, int] = {}
    by_mode: Dict[str, List[Dict[str, Any]]] = {}
    for sig in classified_signals:
        mid = sig.get("failure_mode_id") or "UNKNOWN"
        counts[mid] = counts.get(mid, 0) + 1
        by_mode.setdefault(mid, []).append(sig)
    ranked = sorted(counts.items(), key=lambda x: -x[1])
    return {
        "taxonomy_id": TAXONOMY_ID,
        "total_incidents": len(classified_signals),
        "mode_counts": dict(ranked),
        "top_modes": [{"mode_id": m, "count": c} for m, c in ranked[:5]],
        "by_mode": {k: len(v) for k, v in by_mode.items()},
    }


def enrich_drift_report(drift_report: Dict[str, Any]) -> Dict[str, Any]:
    """Add taxonomy classifications to governance drift report."""
    classified: List[Dict[str, Any]] = []
    for sig in drift_report.get("drift_signals") or []:
        classified.append(classify_drift_signal(sig))
    agg = aggregate_failure_modes(classified)
    out = {**drift_report, "drift_signals": classified, "failure_taxonomy": agg}
    return out
