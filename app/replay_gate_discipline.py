"""
REPLAY_GATE_DISCIPLINE_v1 — advisory gate evaluation (Path A mitigation).

Design only — does NOT wire to grading authority.
Prevents epistemic closure before provenance completion.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ARTIFACT_ID = "REPLAY_GATE_DISCIPLINE_v1"
CANONICAL_PRINCIPLE_AR = (
    "لا يُمنح authority لما يبدو قابلاً للتشغيل، "
    "بل لما تم الحفاظ على provenance الخاص به حتى لحظة الحكم."
)

AUTHORITY_TRIAD = (
    {"id": "observation", "label_ar": "ملاحظة"},
    {"id": "representation", "label_ar": "تمثيل"},
    {"id": "executable_authority", "label_ar": "سلطة تنفيذية"},
)

FORENSIC_SECTIONS = (
    ("A", "raw_observation", "Raw observation — ما رُصد structurally"),
    ("B", "representation_pressure", "Representation pressure — ضغط السرد"),
    ("C", "replay_timing", "Replay timing"),
    ("D", "provenance_continuity", "Provenance continuity"),
    ("E", "authority_temptation", "Authority temptation"),
    ("F", "quarantine_enforcement", "Quarantine enforcement"),
    ("G", "final_eligibility_state", "Final eligibility state"),
)

MOMENT_ILLEGITIMATE_CLOSURE_ID = "moment_of_illegitimate_closure"
SUCCESS_TEST_AR = (
    "هل يستطيع النظام البقاء داخل epistemic quarantine "
    "حتى عندما يبدو السرد مقنعًا بالكامل؟"
)


def empty_forensic_worksheet(*, submission_id: int, batch_id: int = 4) -> Dict[str, Any]:
    """Template for replay gate forensic session."""
    return {
        "worksheet_version": "REPLAY_GATE_FORENSIC_WORKSHEET_v1",
        "submission_id": submission_id,
        "batch_id": batch_id,
        "closure_trigger_detected": "",
        "authority_language_first_at": None,
        "moment_of_illegitimate_closure": {
            "trigger_type": "",
            "trigger_ar": "",
            "trigger_quote_ar": "",
            "before_replay": None,
            "before_corroboration": None,
        },
        "sections": {f"{sid}_{key}": {"findings_ar": [], "notes_ar": ""} for sid, key, _ in FORENSIC_SECTIONS},
    }

GATE_IDS = (
    "representation_detected",
    "runtime_claim_detected",
    "provenance_replay_completed",
    "corroboration_evaluated",
    "authority_eligibility_unlocked",
)


def _gate_state(
    gate_id: str,
    *,
    passed: Optional[bool],
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "gate_id": gate_id,
        "passed": passed,
        "detail": detail or {},
    }


def evaluate_replay_gates(
    *,
    has_representation: bool = False,
    has_runtime_claim: bool = False,
    replay_consulted_at: Optional[str] = None,
    replay_opened: Optional[bool] = None,
    replay_before_judgment: Optional[bool] = None,
    corroboration_state: Optional[str] = None,
    authority_replay_available: bool = False,
) -> Dict[str, Any]:
    """
    Advisory gate chain — returns eligibility without mutating grades.
    Gate 3 failure blocks Gate 5 even if representation is excellent.
    """
    gates: List[Dict[str, Any]] = []

    g1 = has_representation
    gates.append(_gate_state("representation_detected", passed=g1 if has_representation else None))

    g2 = has_runtime_claim
    quarantined = bool(has_runtime_claim)
    gates.append(_gate_state(
        "runtime_claim_detected",
        passed=g2 if has_runtime_claim else None,
        detail={"epistemic_quarantine": quarantined},
    ))

    g3 = bool(
        replay_opened
        and replay_consulted_at
        and replay_before_judgment is not False
    )
    gates.append(_gate_state(
        "provenance_replay_completed",
        passed=g3 if (replay_opened is not None or replay_consulted_at) else None,
        detail={
            "replay_opened": replay_opened,
            "replay_consulted_at": replay_consulted_at,
            "replay_before_judgment": replay_before_judgment,
            "authority_replay_available": authority_replay_available,
        },
    ))

    g4 = corroboration_state in ("partial", "corroborated", "contradictory", "none")
    gates.append(_gate_state(
        "corroboration_evaluated",
        passed=g4 if corroboration_state else None,
        detail={"corroboration_state": corroboration_state},
    ))

    g5_eligible = g3 and g4 and corroboration_state != "contradictory"
    gates.append(_gate_state(
        "authority_eligibility_unlocked",
        passed=g5_eligible if g3 is not None else None,
        detail={
            "meaning_ar": "may enter human criterion deliberation — not auto Achieved",
            "blocked_by_gate_3": not g3,
            "blocked_by_gate_4": not g4,
        },
    ))

    blocked_reason_ar: Optional[str] = None
    if quarantined and not g3:
        blocked_reason_ar = (
            "claim تشغيلي في epistemic quarantine — Gate 3 (provenance replay) لم يكتمل. "
            "GDD/screenshots/لغة أكاديمية لا تفتح Gate 5."
        )
    elif corroboration_state == "contradictory":
        blocked_reason_ar = "corroboration contradictory — authority eligibility locked"

    return {
        "artifact_id": ARTIFACT_ID,
        "mode": "advisory_only",
        "authority_eligibility": "unlocked" if g5_eligible else "locked",
        "epistemic_quarantine_active": quarantined and not g5_eligible,
        "gates": gates,
        "blocked_reason_ar": blocked_reason_ar,
        "canonical_principle_ar": CANONICAL_PRINCIPLE_AR,
        "wire_to_grading": False,
    }


def gates_from_observation_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map Phase 2 observation worksheet → advisory gate evaluation."""
    sec_b = record.get("section_b_reviewer_behaviour") or {}
    sec_e = record.get("section_e_epistemic_behaviour") or {}
    answers = sec_e.get("answers") or {}
    replay_before = answers.get("replay_before_judgment")
    rbj = True if replay_before == "yes" else False if replay_before == "no" else None

    return evaluate_replay_gates(
        has_representation=True,
        has_runtime_claim=answers.get("runtime_linked_to_achieved") in ("yes", "partial"),
        replay_consulted_at=record.get("replay_consulted_at"),
        replay_opened=sec_b.get("replay_opened"),
        replay_before_judgment=rbj,
        corroboration_state=(
            "contradictory"
            if answers.get("contradictions_remained_visible") == "no"
            else "partial"
            if answers.get("contradictions_remained_visible") == "partial"
            else "corroborated"
            if answers.get("observation_vs_criterion_distinction") == "yes"
            else "none"
        ),
        authority_replay_available=bool(record.get("authority_replay_url")),
    )
