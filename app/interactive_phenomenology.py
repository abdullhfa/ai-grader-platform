"""
Interactive phenomenology — mechanic observation without pedagogical inference.

Canonical descriptors: PHENOMENOLOGY_MANIFEST_v1.json (interactive domain)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.phenomenology_manifest import (
    MANIFEST_ID,
    descriptors as _descriptors,
    domain_invariant,
    escalation_pairs as _escalation_pairs,
    forbidden_escalations as _forbidden_escalations,
)

SPEC_ID = "MANUAL_PLAYTEST_PASS_v1"
PRIMARY_INVARIANT_EN = domain_invariant("interactive")
PHENOMENOLOGY_DESCRIPTORS = _descriptors("interactive")
FORBIDDEN_ESCALATIONS = _forbidden_escalations("interactive")
ESCALATION_PAIRS: List[Tuple[str, str]] = _escalation_pairs("interactive")

FORBIDDEN_RECORD_PATTERNS: List[Tuple[str, str]] = [
    (r"\bgame\s+validated\b", "mechanic observed — no legitimacy"),
    (r"\brubric\s+(achieved|failed)\b", "mechanic observed — no rubric inference"),
    (r"\bproject\s+invalid\b", "level transition failed — observation only"),
    (r"\bgameplay\s+broken\b", "input conflict — observation only"),
    (r"\bachievement\s+impossible\b", "respawn inconsistent — observation only"),
    (r"\bmechanics\s+validated\b", "interactive phenomenology — no validation"),
    (r"اللعبة\s+ناجحة", "mechanic observed — no legitimacy"),
    (r"فشل\s+المشروع", "observation only — no project invalidity claim"),
]


def build_interactive_phenomenology_record(
    descriptors: List[str],
    *,
    t_offset_ms: int = 0,
    detail: Dict[str, Any] | None = None,
    source: str = "manual_playtest",
) -> Dict[str, Any]:
    unknown = [d for d in descriptors if d not in PHENOMENOLOGY_DESCRIPTORS]
    if unknown:
        raise ValueError(f"unknown interactive phenomenology descriptor(s): {', '.join(unknown)}")
    out = list(descriptors)
    if "mechanic_observed_without_pedagogical_inference" not in out and out:
        out.insert(0, "mechanic_observed_without_pedagogical_inference")
    return {
        "manifest_id": MANIFEST_ID,
        "domain": "interactive",
        "spec_id": SPEC_ID,
        "layer": "interactive_phenomenology",
        "descriptors": out,
        "t_offset_ms": t_offset_ms,
        "source": source,
        "detail": detail or {},
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def validate_playtest_record_text(text: str) -> Dict[str, Any]:
    violations: List[Dict[str, str]] = []
    lower = (text or "").lower()
    for forbidden in FORBIDDEN_ESCALATIONS:
        token = forbidden.replace("_", " ")
        if token in lower or forbidden in lower:
            violations.append({"type": "forbidden_escalation", "phrase": forbidden})
    for pattern, suggested in FORBIDDEN_RECORD_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            violations.append({"type": "pattern", "pattern": pattern, "suggested": suggested})
    return {
        "manifest_id": MANIFEST_ID,
        "domain": "interactive",
        "allowed": len(violations) == 0,
        "violations": violations,
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def describe_interactive_phenomenology_en(descriptors: List[str]) -> str:
    labels = {
        "mechanic_observed_without_pedagogical_inference": (
            "Interactive mechanic signals were observed without pedagogical inference."
        ),
        "start_state_transition_observed": "Start-state transition was observed after input.",
        "start_state_transition_not_observed": "Start-state transition was not observed after input.",
        "jump_response_observed": "Jump response was observed after start.",
        "score_change_observed": "Score change was observed on cup collection.",
        "level_transition_observed": "Level transition was observed after third cup.",
        "level_transition_failed": "Level transition failure was observed after third cup.",
        "timer_expired_no_consequence_observed": (
            "Timer reached zero with no gameplay consequence observed."
        ),
        "respawn_observed": "Player respawn was observed between life losses.",
        "game_over_panel_observed": "Game over panel was observed after lives exhausted.",
        "input_conflict_observed": "Input conflict was observed (Space dual-use or similar).",
    }
    parts = [labels.get(d, d) for d in descriptors if d in PHENOMENOLOGY_DESCRIPTORS]
    summary = " ".join(parts) if parts else "No interactive phenomenology recorded."
    check = validate_playtest_record_text(summary)
    if not check["allowed"]:
        raise ValueError("interactive phenomenology summary failed escalation check")
    return summary + " Pedagogical and rubric meaning remain unverified."
