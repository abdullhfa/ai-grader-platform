"""
Architectural hardening — clarity under restraint, not feature expansion.

Question: Can the architecture become smaller without losing constitutional protections?
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

PHASE_ID = "ARCHITECTURAL_HARDENING_v1"
CORE_ARTIFACT = (
    Path(__file__).resolve().parent
    / "calibration"
    / "CONSTITUTIONAL_CORE_INVARIANTS_v1.json"
)

OVERLOAD_SURFACE_CATALOG: List[str] = [
    "PHENOMENOLOGY_MANIFEST_v1",
    "QUARANTINE_DOMAIN_SPLIT_v1",
    "RUNTIME_OBSERVABILITY_PREPARATION_v1",
    "PROVENANCE_AWARE_EXECUTION_SANDBOX_SPEC_v1",
    "TELEMETRY_REPLAY_CAPTURE_WIRING_v1",
    "RUNTIME_EPISTEMIC_GOVERNANCE_v1",
    "RUNTIME_QUARANTINE_STATES_v1",
    "LIVE_CONSTITUTIONAL_VALIDATION_v1",
    "OBSERVATORY_POSTURE_GOVERNANCE_v1",
    "CONSTITUTIONAL_CORE_INVARIANTS_v1",
]

OVERLOAD_THRESHOLD = 10


def load_constitutional_core() -> Dict[str, Any]:
    return json.loads(CORE_ARTIFACT.read_text(encoding="utf-8"))


def assess_architecture_overload(
    *,
    additional_surfaces: int = 0,
) -> Dict[str, Any]:
    """Advisory — high spec surface count increases organizational gravity risk."""
    surface_count = len(OVERLOAD_SURFACE_CATALOG) + additional_surfaces
    overload_risk = surface_count >= OVERLOAD_THRESHOLD
    return {
        "phase_id": PHASE_ID,
        "surface_count": surface_count,
        "overload_risk_detected": overload_risk,
        "supreme_risk_en": "epistemic architecture overload",
        "advisory_en": (
            "High conceptual surface area may itself produce organizational gravity. "
            "Prefer distillation over expansion."
        ),
        "recommended_action_en": "reduce surface area — do not add layers",
        "hardening_question_en": (
            "Can the architecture become smaller without losing its constitutional protections?"
        ),
    }


def hardening_gate_review(
    *,
    simplifies: bool,
    preserves_core_invariants: bool,
    adds_layers: bool = False,
) -> Dict[str, Any]:
    """Gate for any change during hardening phase."""
    core = load_constitutional_core()
    if adds_layers:
        return {
            "allowed": False,
            "reason_en": "Hardening phase forbids adding layers.",
            "recommended_action_en": "reduce surface area",
        }
    if not preserves_core_invariants:
        return {
            "allowed": False,
            "reason_en": "Change would weaken constitutional core.",
            "core_invariant_count": core.get("count"),
        }
    illuminates = simplifies and preserves_core_invariants
    organizes = adds_layers or (not simplifies and surface_count_risk())
    return {
        "allowed": illuminates and not organizes,
        "illuminates": illuminates,
        "organizes_cognition": organizes,
        "core_preserved": preserves_core_invariants,
        "gate_question_en": "Does simplification illuminate? Or does complexity organize cognition?",
    }


def surface_count_risk() -> bool:
    return len(OVERLOAD_SURFACE_CATALOG) >= OVERLOAD_THRESHOLD


def step_6_readiness() -> Dict[str, Any]:
    """Capability vs legitimacy split — Step 6 constitutionally blocked."""
    return {
        "step_6_capability": "ready",
        "step_6_legitimacy": "blocked",
        "invariant_en": "Capability built ≠ legitimacy granted.",
        "evidence_gaps": {
            "live_constitutional_evidence": "paused",
            "human_disagreement_evidence": "absent",
            "non_coercive_observability_proof": "absent",
            "runtime_psychological_posture_evidence": "absent",
            "organizational_gravity_counter_evidence": "absent",
        },
        "ledger_intentionally_empty": True,
        "recommended_next": "architectural_hardening",
        "not_recommended": "step_6_activation",
    }
