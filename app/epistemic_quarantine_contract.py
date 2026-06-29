"""
EPISTEMIC_QUARANTINE_CONTRACT_v1 — constitutional state machine (Path A).

Design only — does NOT wire to grading authority.
Epistemic execution boundary with irreversible audit residue.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_ID = "EPISTEMIC_QUARANTINE_CONTRACT_v1"
CANONICAL_AXIOM_AR = (
    "Quarantine لا يعني أن الادعاء خاطئ، "
    "بل يعني أن شرعيته لم تكتمل بعد."
)

STATES = (
    "idle",
    "quarantine_entered",
    "quarantine_maintained",
    "lifting_in_progress",
    "quarantine_lifted",
    "breach_detected",
)

ENTRY_TRIGGERS = (
    "T_RUNTIME_CLAIM_NO_REPLAY",
    "T_EXECUTABLE_NO_PROVENANCE",
    "T_SCREENSHOTS_NO_CORROBORATION",
    "T_VERIFICATION_LEXICON_PRE_GATE3",
    "T_CONTRADICTION_UNRESOLVED",
)

ALLOWED_ACTIONS = (
    "A_OBSERVATION",
    "A_REPRESENTATION_PARSE",
    "A_ARTIFACT_INDEX",
    "A_DESCRIPTIVE_INFERENCE",
    "A_REPLAY_REQUEST",
)

FORBIDDEN_ACTIONS = (
    "F_ACHIEVED_ASSIGNMENT",
    "F_VERIFICATION_WORDING",
    "F_AUTHORITY_ESCALATION",
    "F_GRADING_CLOSURE",
    "F_RUNTIME_CONFIRMATION",
)

LIFT_STEPS = (
    "LIFT_REPLAY_COMPLETED",
    "LIFT_RUNTIME_CORROBORATED",
    "LIFT_PROVENANCE_CONTINUITY",
    "LIFT_CONTRADICTIONS_BOUNDED",
    "LIFT_HUMAN_ACK",
    "LIFT_COMPLETE",
)

BREACH_LEVELS = ("QB1", "QB2", "QB3", "QB4")

AUDIT_LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "epistemic_quarantine_audit.jsonl"
)


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def evaluate_entry_triggers(
    *,
    has_runtime_claim: bool = False,
    replay_consulted_at: Optional[str] = None,
    executable_detected: bool = False,
    gameplay_verified: bool = False,
    provenance_linked: bool = False,
    visual_inference_without_corroboration: bool = False,
    verification_language_before_gate3: bool = False,
    contradiction_unresolved: bool = False,
) -> List[str]:
    """Return fired mandatory entry trigger IDs."""
    fired: List[str] = []
    if has_runtime_claim and not replay_consulted_at:
        fired.append("T_RUNTIME_CLAIM_NO_REPLAY")
    if executable_detected and (not gameplay_verified or not provenance_linked):
        fired.append("T_EXECUTABLE_NO_PROVENANCE")
    if visual_inference_without_corroboration:
        fired.append("T_SCREENSHOTS_NO_CORROBORATION")
    if verification_language_before_gate3:
        fired.append("T_VERIFICATION_LEXICON_PRE_GATE3")
    if contradiction_unresolved:
        fired.append("T_CONTRADICTION_UNRESOLVED")
    return fired


def resolve_quarantine_state(
    *,
    entry_triggers: List[str],
    gate_eval: Optional[Dict[str, Any]] = None,
    breach_detected: bool = False,
    lift_steps_completed: Optional[List[str]] = None,
) -> str:
    """Map triggers + gate eval → constitutional state."""
    if not entry_triggers:
        return "idle"
    if breach_detected:
        return "breach_detected"

    lift_steps_completed = lift_steps_completed or []
    gate_eval = gate_eval or {}

    if (
        gate_eval.get("authority_eligibility") == "unlocked"
        and "LIFT_HUMAN_ACK" in lift_steps_completed
    ):
        return "quarantine_lifted"
    if "LIFT_REPLAY_COMPLETED" in lift_steps_completed:
        return "lifting_in_progress"
    if entry_triggers:
        return "quarantine_maintained"
    return "quarantine_entered"


def is_action_permitted(action_id: str, *, quarantine_active: bool) -> bool:
    if not quarantine_active:
        return True
    if action_id in FORBIDDEN_ACTIONS:
        return False
    return action_id in ALLOWED_ACTIONS


def evaluate_lift_protocol(
    *,
    replay_completed: bool,
    runtime_corroborated: bool,
    provenance_continuity: bool,
    contradictions_bounded: bool,
    human_ack: bool,
) -> Dict[str, Any]:
    """Step-wise lift evaluation — returns completed steps and blocking step."""
    steps = [
        ("LIFT_REPLAY_COMPLETED", replay_completed),
        ("LIFT_RUNTIME_CORROBORATED", runtime_corroborated),
        ("LIFT_PROVENANCE_CONTINUITY", provenance_continuity),
        ("LIFT_CONTRADICTIONS_BOUNDED", contradictions_bounded),
        ("LIFT_HUMAN_ACK", human_ack),
    ]
    completed: List[str] = []
    blocked_at: Optional[str] = None
    for step_id, ok in steps:
        if ok:
            completed.append(step_id)
        else:
            blocked_at = step_id
            break
    if blocked_at is None:
        completed.append("LIFT_COMPLETE")
    return {
        "completed_steps": completed,
        "blocked_at": blocked_at,
        "lift_complete": blocked_at is None,
    }


def classify_breach_severity(
    *,
    verification_before_replay: bool = False,
    runtime_achieved_without_provenance: bool = False,
    authority_grant_contradiction_open: bool = False,
    descriptive_drift_only: bool = False,
) -> Optional[str]:
    """QB1–QB4 taxonomy — highest matching severity wins."""
    if authority_grant_contradiction_open:
        return "QB4"
    if runtime_achieved_without_provenance:
        return "QB3"
    if verification_before_replay:
        return "QB2"
    if descriptive_drift_only:
        return "QB1"
    return None


def build_audit_residue(
    *,
    submission_id: int,
    event_type: str,
    state_from: str,
    state_to: str,
    entry_triggers: Optional[List[str]] = None,
    temptation_detected_at: Optional[str] = None,
    escalation_events: Optional[List[str]] = None,
    breach_severity: Optional[str] = None,
    lift_basis: Optional[Dict[str, Any]] = None,
    lifted_by: Optional[str] = None,
    lineage_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Epistemic audit residue record — append-only semantics."""
    audit_id = f"eqa_{uuid.uuid4().hex[:12]}"
    payload = {
        "artifact_id": ARTIFACT_ID,
        "audit_id": audit_id,
        "submission_id": submission_id,
        "event_type": event_type,
        "state_from": state_from,
        "state_to": state_to,
        "entry_triggers": entry_triggers or [],
        "temptation_detected_at": temptation_detected_at,
        "escalation_events": escalation_events or [],
        "breach_severity": breach_severity,
        "lift_basis": lift_basis,
        "lifted_by": lifted_by,
        "recorded_at": _now_iso(),
        "lineage_refs": lineage_refs or [],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    payload["residue_digest"] = digest
    return payload


def append_audit_residue(record: Dict[str, Any], *, ledger_path: Optional[Path] = None) -> str:
    """Append audit residue to jsonl ledger (advisory — creates file if missing)."""
    path = ledger_path or AUDIT_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(record.get("audit_id", ""))


def evaluate_from_observation_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full advisory quarantine eval from Phase 2 observation + replay gates."""
    from app.replay_gate_discipline import gates_from_observation_record

    gate_eval = gates_from_observation_record(record)
    sec_b = record.get("section_b_reviewer_behaviour") or {}
    sec_e = record.get("section_e_epistemic_behaviour") or {}
    answers = sec_e.get("answers") or {}

    triggers = evaluate_entry_triggers(
        has_runtime_claim=answers.get("runtime_linked_to_achieved") in ("yes", "partial"),
        replay_consulted_at=record.get("replay_consulted_at"),
        executable_detected=answers.get("modality_dominance_observed") in ("yes", "partial"),
        gameplay_verified=False,
        provenance_linked=answers.get("observation_vs_criterion_distinction") == "yes",
        visual_inference_without_corroboration=answers.get("modality_dominance_observed") == "partial",
        verification_language_before_gate3=(
            answers.get("verification_language_used") == "yes"
            and not record.get("replay_consulted_at")
        ),
        contradiction_unresolved=answers.get("contradictions_remained_visible") in ("no", "partial"),
    )

    verification_before_replay = (
        answers.get("verification_language_used") == "yes"
        and sec_b.get("replay_consulted_at") is None
    )
    breach = classify_breach_severity(
        verification_before_replay=verification_before_replay,
        runtime_achieved_without_provenance=(
            answers.get("runtime_linked_to_achieved") == "yes"
            and gate_eval.get("authority_eligibility") == "locked"
        ),
        authority_grant_contradiction_open=(
            answers.get("contradictions_remained_visible") == "no"
            and answers.get("runtime_linked_to_achieved") == "yes"
        ),
    )

    state = resolve_quarantine_state(
        entry_triggers=triggers,
        gate_eval=gate_eval,
        breach_detected=breach in ("QB2", "QB3", "QB4"),
    )

    return {
        "artifact_id": ARTIFACT_ID,
        "mode": "advisory_only",
        "canonical_axiom_ar": CANONICAL_AXIOM_AR,
        "submission_id": record.get("submission_id"),
        "quarantine_state": state,
        "entry_triggers": triggers,
        "quarantine_active": state in (
            "quarantine_entered",
            "quarantine_maintained",
            "lifting_in_progress",
            "breach_detected",
        ),
        "breach_severity": breach,
        "gate_eval": gate_eval,
        "wire_to_grading": False,
    }
