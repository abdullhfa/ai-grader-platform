"""
Constitutional maintenance — maintaining restraint while reducing structural weight.

Central question: Does the architecture now require less belief to trust its restraint?
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.architectural_hardening import assess_architecture_overload, load_constitutional_core, step_6_readiness
from app.redundancy_audit import explanation_burden_check, load_hardening_merge_log, run_redundancy_audit

PHASE_ID = "CONSTITUTIONAL_MAINTENANCE_v1"
GATE_REVIEW_PATH = (
    Path(__file__).resolve().parent
    / "calibration"
    / "HARDENING_GATE_REVIEW_v1.json"
)
LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "runtime_observation_ledger.jsonl"
)

CENTRAL_QUESTION_EN = (
    "Does the architecture now require less belief to trust its restraint?"
)
SUPREME_SUCCESS_EN = "We still refuse to declare ourselves justified."
SUPREME_RISK_EN = (
    "People trusting the doctrine instead of observing the restraint directly."
)
MAINTENANCE_INVARIANT_EN = (
    "Restraint must remain stronger than institutional self-legitimation."
)


def _ledger_empty() -> bool:
    return not LEDGER.exists() or LEDGER.read_text(encoding="utf-8").strip() == ""


def run_hardening_gate_review() -> Dict[str, Any]:
    """Step 4 gate review — observational, not self-certifying."""
    merge_log = load_hardening_merge_log("HARDENING_MERGE_1")
    merge_check = merge_log.get("explanation_burden_check") or {}
    burden = explanation_burden_check(
        merge_id="HARDENING_MERGE_1",
        canonical_surfaces_before=int(merge_check.get("canonical_json_surfaces_before") or 3),
        canonical_surfaces_after=int(merge_check.get("canonical_json_surfaces_after") or 2),
        interpretive_power_increased=bool(merge_check.get("interpretive_power_increased")),
        legitimacy_surface_expanded=bool(merge_check.get("legitimacy_surface_expanded")),
        abstraction_layer_added=False,
    )
    ledger_empty = _ledger_empty()
    overload = assess_architecture_overload()
    core = load_constitutional_core()
    merge_reduced = bool(merge_check.get("explanation_burden_reduced", burden.get("passed")))
    requires_less_belief = (
        burden.get("passed")
        and ledger_empty
        and merge_reduced
        and not bool(merge_check.get("interpretive_power_increased"))
    )
    doctrine_literacy_required = not burden.get("passed")
    overload_watch = bool(overload.get("overload_risk_detected"))
    return {
        "phase_id": PHASE_ID,
        "review_id": "HARDENING_GATE_REVIEW_v1",
        "central_question_en": CENTRAL_QUESTION_EN,
        "requires_less_belief_to_trust_restraint": requires_less_belief,
        "supreme_success_en": SUPREME_SUCCESS_EN if ledger_empty else "VIOLATED — ledger not empty",
        "supreme_risk_en": SUPREME_RISK_EN,
        "maintenance_invariant_en": MAINTENANCE_INVARIANT_EN,
        "explanation_burden_check": burden,
        "merge_1_log": merge_log,
        "ledger_empty": ledger_empty,
        "self_certification_refused": ledger_empty,
        "architecture_health": {
            "protection_clearer": burden.get("passed"),
            "doctrine_literacy_required": doctrine_literacy_required,
            "overload_watch": overload_watch,
            "expert_only_machinery_risk": (
                "elevated" if doctrine_literacy_required else "low_after_merge_1"
            ),
        },
        "constitutional_core_count": core.get("count"),
        "overload_assessment": overload,
        "step_6_readiness": step_6_readiness(),
        "gate_verdict": {
            "passed": requires_less_belief and ledger_empty,
            "step_6_still_blocked": True,
            "recommended_mode": PHASE_ID,
            "not_recommended": ["step_6", "feature_expansion", "doctrine_expansion"],
        },
        "assigns_legitimacy": False,
    }


def maintenance_status() -> Dict[str, Any]:
    """Current constitutional maintenance posture."""
    gate = run_hardening_gate_review()
    audit = run_redundancy_audit()
    return {
        "phase_id": PHASE_ID,
        "mode": "maintaining_restraint_reducing_weight",
        "central_question_en": CENTRAL_QUESTION_EN,
        "gate_review": gate,
        "redundancy_audit_ledger_empty": audit.get("ledger_empty_confirmed"),
        "path_decision": "pending_facilitator",
        "forbidden": [
            "step_6_activation",
            "feature_expansion",
            "doctrine_expansion",
            "ledger_self_certification",
        ],
    }
