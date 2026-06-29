"""
Runtime Observation Contract v1 — language and authority constants for L4.

Sandbox not implemented. This module freezes semantics before any runtime execution.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Tuple

CONTRACT_ID = "RUNTIME_OBSERVATION_CONTRACT_v1"
L4_PHENOMENOLOGY_CLAUSE_ID = "RUNTIME_L4_PHENOMENOLOGY_CLAUSE_v1"
L4_PHENOMENOLOGY_CLAUSE_EN = (
    "L4 may observe runtime phenomenology. L4 may not infer gameplay legitimacy."
)
L4_PHENOMENOLOGY_MAY = (
    "observe_runtime_phenomenology",
    "record_phenomenological_traces",
    "apply_runtime_quarantine_states",
    "link_provenance_segments_observation_only",
)
L4_PHENOMENOLOGY_MAY_NOT = (
    "infer_gameplay_legitimacy",
    "infer_rubric_satisfaction",
    "infer_mechanics_validated",
    "infer_submission_authentic",
    "collapse_telemetry_to_meaning",
    "auto_merge_governance_layers",
)
MAX_AUTO_LEVEL_WITH_SANDBOX = 4  # L4 = observation only; L5 = human

# Allowed institutional claims at L4
L4_ALLOWED_CLAIMS_EN: FrozenSet[str] = frozenset({
    "runtime_observed",
    "executable_launched_in_sandbox",
    "limited_runtime_observations_collected",
    "gameplay_hints",
    "interaction_traces_detected",
    "runtime_stable",
    "telemetry_corroborated",
    "operational_evidence_advisory",
})

L4_FORBIDDEN_CLAIMS_EN: FrozenSet[str] = frozenset({
    "game_completed",
    "criteria_verified",
    "gameplay_confirmed",
    "criterion_achieved_from_runtime",
    "verified_achievement",
    "game_verified",
    "runtime_behaviour_verified",
    "gameplay_legitimacy_inferred",
    "gameplay_understood",
    "mechanics_validated",
})

L4_FORBIDDEN_PATTERNS: List[Tuple[str, str]] = [
    (r"\bgame\s+completed\b", "runtime observations collected"),
    (r"\bcriteria\s+verified\b", "operational evidence advisory"),
    (r"\bgameplay\s+confirmed\b", "interaction traces detected"),
    (r"\bverified\s+achievement\b", "human review required"),
    (r"تم\s+التحقق\s+من\s+المعيار", "مراجعة بشرية مطلوبة"),
    (r"اللعبة\s+مكتملة", "observations collected under controlled conditions"),
]

RUNTIME_SIGNAL_SCHEMA: Dict[str, str] = {
    "scene_loaded": "yes|no|unknown",
    "player_moved": "detected|not_detected|unknown",
    "score_changed": "yes|no|unknown",
    "collision_events": "observed|none|unknown",
    "level_transition": "partial|full|none|unknown",
    "crash": "none|observed|unknown",
}

RUNTIME_CRITERION_HINT_MAP: Dict[str, List[str]] = {
    "scoring_system": ["score_changed"],
    "movement": ["player_moved"],
    "health_lives": ["hud_variation"],
    "level_progression": ["level_transition", "scene_loaded"],
    "ui_interaction": ["menu_navigation"],
}


def get_l4_phenomenology_clause() -> Dict[str, Any]:
    """Canonical L4 phenomenology clause — compressed from standalone JSON."""
    return {
        "clause_id": L4_PHENOMENOLOGY_CLAUSE_ID,
        "parent_contract": CONTRACT_ID,
        "canonical": True,
        "clause_en": L4_PHENOMENOLOGY_CLAUSE_EN,
        "may": list(L4_PHENOMENOLOGY_MAY),
        "may_not": list(L4_PHENOMENOLOGY_MAY_NOT),
        "note_en": "Runtime temptation is psychologically stronger than narrative temptation.",
    }


def validate_l4_claim_text(text: str) -> Dict[str, Any]:
    """Check text against L4 contract — for future sandbox output sanitization."""
    import re

    violations: List[Dict[str, str]] = []
    lower = (text or "").lower()
    for forbidden in L4_FORBIDDEN_CLAIMS_EN:
        if forbidden.replace("_", " ") in lower or forbidden in lower:
            violations.append({"type": "forbidden_claim", "phrase": forbidden})
    for pattern, replacement in L4_FORBIDDEN_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            violations.append({"type": "pattern", "pattern": pattern, "suggested": replacement})
    return {
        "contract_id": CONTRACT_ID,
        "allowed": len(violations) == 0,
        "violations": violations,
        "max_auto_level": MAX_AUTO_LEVEL_WITH_SANDBOX,
        "l4_phenomenology_clause_en": L4_PHENOMENOLOGY_CLAUSE_EN,
        "note_ar": "L4 observation ≠ L5 verified achievement",
    }
