"""Hallucination guard — claims must map to evidence graph nodes."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.ai_reasoning.evidence_graph import CriterionEvidenceGraph

_CLAIM_PATTERNS = {
    "win_detected": re.compile(r"\b(win|victory|فوز|انتصار)\b", re.I),
    "lose_detected": re.compile(r"\b(lose|game over|defeat|خسارة)\b", re.I),
    "movement_detected": re.compile(r"\b(movement|player moved|تحرك|gameplay loop)\b", re.I),
    "crash_detected": re.compile(r"\b(crash|crashed|تعطل)\b", re.I),
    "freeze_detected": re.compile(r"\b(freeze|frozen|stuck|متجمد)\b", re.I),
    "runtime_observed": re.compile(r"\b(runtime|executed|launched|تشغيل)\b", re.I),
    "score_hud_detected": re.compile(r"\b(score|health|points|نقاط)\b", re.I),
}

_CLAIM_TO_EVIDENCE = {
    "win_detected": ["win_detected", "win_not_detected"],
    "lose_detected": ["lose_detected", "lose_not_detected"],
    "movement_detected": ["movement_detected", "static_scene", "motion_present"],
    "crash_detected": ["crash_detected"],
    "freeze_detected": ["freeze_detected", "motion_present"],
    "runtime_observed": ["runtime_observed"],
    "score_hud_detected": ["score_hud_detected", "hud_text_extracted"],
}


def extract_claims(text: str) -> List[str]:
    claims = []
    for claim, pattern in _CLAIM_PATTERNS.items():
        if pattern.search(text or ""):
            claims.append(claim)
    return claims


def validate_claim_against_graph(
    claim: str,
    graph: CriterionEvidenceGraph,
) -> Tuple[bool, str]:
    allowed_labels = _CLAIM_TO_EVIDENCE.get(claim, [])
    node_labels = {n.label for n in graph.evidence_nodes}
    supporting = set(graph.supporting_events)

    if claim in ("win_detected", "lose_detected", "movement_detected"):
        if any(l in node_labels or l in supporting for l in allowed_labels):
            if claim == "win_detected" and "win_detected" in node_labels:
                return True, "win_event_or_detection_present"
            if claim == "movement_detected" and (
                "movement_detected" in node_labels or "motion_present" in node_labels
            ):
                return True, "motion_evidence_present"
            if claim == "lose_detected" and "lose_detected" in node_labels:
                return True, "lose_event_present"
        return False, f"missing_evidence_for_{claim}"

    if any(l in node_labels or l in supporting for l in allowed_labels):
        return True, "evidence_node_match"
    return False, f"unverified_claim_{claim}"


def guard_reasoning_text(
    text: str,
    graphs: List[CriterionEvidenceGraph],
) -> Dict[str, Any]:
    claims = extract_claims(text)
    flags: List[Dict[str, Any]] = []
    graph = graphs[0] if graphs else CriterionEvidenceGraph(criterion="general")

    for claim in claims:
        ok, reason = validate_claim_against_graph(claim, graph)
        if not ok:
            flags.append(
                {
                    "claim": claim,
                    "reason": reason,
                    "reasoning_rejected": True,
                }
            )

    return {
        "claims_detected": claims,
        "flags": flags,
        "reasoning_rejected": len(flags) > 0,
        "guard_version": "hallucination_guard_v1",
    }
