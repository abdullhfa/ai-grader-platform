"""AI Reliability Layer — hallucination reduction, confidence, disagreement detection."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.ai.reliability")

RELIABILITY_VERSION = "ai_reliability_v1"

_OVERCLAIM = re.compile(
    r"\b(verified|confirmed|100%|definitely achieved|مؤكد|تم التحقق)\b",
    re.IGNORECASE,
)
_NO_EVIDENCE = re.compile(
    r"\b(clearly demonstrates|obviously|without doubt|بوضوح|بلا شك)\b",
    re.IGNORECASE,
)


def score_ai_confidence(
    grading_result: Dict[str, Any],
    *,
    evidence_gate: Optional[Dict[str, Any]] = None,
    runtime_validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute composite confidence from evidence + AI output consistency."""
    ai_likelihood = float(grading_result.get("ai_likelihood") or 0)
    criteria = grading_result.get("criteria_results") or []
    achieved_count = sum(1 for c in criteria if isinstance(c, dict) and c.get("achieved"))
    gate_gaps = bool((evidence_gate or {}).get("has_gaps"))
    smoke = ((runtime_validation or {}).get("functional_smoke") or {}).get(
        "functional_smoke_pass"
    )

    evidence_factor = 0.85
    if gate_gaps:
        evidence_factor = 0.45
    if smoke is True:
        evidence_factor = min(1.0, evidence_factor + 0.15)
    elif smoke is False:
        evidence_factor = max(0.2, evidence_factor - 0.2)

    # High AI-likelihood text + many achieved = lower trust
    hallucination_risk = "low"
    if ai_likelihood >= 70 and achieved_count >= 3 and gate_gaps:
        hallucination_risk = "high"
    elif ai_likelihood >= 50 and gate_gaps:
        hallucination_risk = "medium"

    confidence = round(max(0.0, min(1.0, evidence_factor * (1 - ai_likelihood / 200))), 3)
    return {
        "composite_confidence": confidence,
        "evidence_factor": evidence_factor,
        "ai_likelihood": ai_likelihood,
        "hallucination_risk": hallucination_risk,
        "achieved_count": achieved_count,
    }


def detect_feedback_disagreements(grading_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag criteria where feedback claims achievement but achieved=False."""
    flags: List[Dict[str, Any]] = []
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        fb = str(cr.get("feedback") or cr.get("reasoning") or "")
        achieved = bool(cr.get("achieved"))
        if not achieved and _OVERCLAIM.search(fb):
            flags.append(
                {
                    "criteria_level": cr.get("criteria_level"),
                    "kind": "overclaim_in_not_achieved",
                    "preview": fb[:200],
                }
            )
        if achieved and _NO_EVIDENCE.search(fb) and not cr.get("covered_points"):
            flags.append(
                {
                    "criteria_level": cr.get("criteria_level"),
                    "kind": "weak_evidence_achieved",
                    "preview": fb[:200],
                }
            )
    return flags


def apply_ai_reliability_layer(
    grading_result: Dict[str, Any],
    *,
    evidence_gate: Optional[Dict[str, Any]] = None,
    runtime_validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    confidence = score_ai_confidence(
        grading_result,
        evidence_gate=evidence_gate,
        runtime_validation=runtime_validation,
    )
    disagreements = detect_feedback_disagreements(grading_result)
    flags = list(grading_result.get("claim_authority_flags") or {})
    if disagreements:
        if isinstance(flags, dict):
            flags.setdefault("ai_reliability", disagreements)
        else:
            flags = {"ai_reliability": disagreements}

    grading_result["ai_reliability"] = {
        "version": RELIABILITY_VERSION,
        "confidence": confidence,
        "disagreements": disagreements,
        "fallback_recommend_human_review": confidence["hallucination_risk"] in ("high", "medium"),
    }
    if disagreements:
        grading_result["claim_authority_flags"] = flags

    logger.info(
        "ai_reliability confidence=%.3f risk=%s disagreements=%d",
        confidence["composite_confidence"],
        confidence["hallucination_risk"],
        len(disagreements),
    )
    return grading_result
