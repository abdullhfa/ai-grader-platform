"""
L4 Institutional Decision Point — epoch review package before sandbox / v2 activation.

At pilot completion the system is at the L4 institutional decision point —
not «start coding sandbox immediately».
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import ACTIVE_FREEZE_EPOCH, FREEZE_EPOCHS
from app.governance_freeze_registry import (
    VERDICT_ACTIVATES_V2,
    build_freeze_registry_report,
    get_l4_gate_status,
)

DECISION_POINT_ID = "L4_institutional_decision_point"

ORDERED_STEPS: List[Dict[str, str]] = [
    {"step": 1, "id": "epoch_workshop_review", "label_ar": "Governance Epoch Workshop Review"},
    {"step": 2, "id": "signed_institutional_verdict", "label_ar": "Signed institutional epoch verdict"},
    {"step": 3, "id": "governance_freeze_v2", "label_ar": "GOVERNANCE_FREEZE_v2 RFC activation"},
    {"step": 4, "id": "minimal_l4_sandbox", "label_ar": "Minimal L4 sandbox (observational only)"},
    {"step": 5, "id": "runtime_telemetry_graph", "label_ar": "Runtime telemetry graph"},
    {"step": 6, "id": "runtime_replay_ui", "label_ar": "Runtime replay UI for human reviewers"},
    {"step": 7, "id": "human_runtime_moderation", "label_ar": "Human runtime authority (L5 mandatory)"},
    {"step": 8, "id": "limited_deployment", "label_ar": "Limited institutional deployment"},
]

REVIEW_DIMENSIONS = (
    "replay_trust",
    "canonical_drift",
    "l3_confusion",
    "unresolved_s5",
    "modality_dominance",
    "mitigation_effectiveness",
)


def _band_ok(band: str) -> bool:
    return band in ("green", "amber")


def _review_replay_trust(narrative: Dict[str, Any], workshop_q: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    rt = narrative.get("replay_trust_state") or {}
    state = rt.get("state", "unknown")
    band = "green" if state == "canonical_trusted" else (
        "amber" if state == "governance_stabilizing" else "red"
    )
    return {
        "dimension": "replay_trust",
        "question_ar": "هل المراجعون اعتمدوا replay؟",
        "auto_band": band,
        "evidence": {
            "replay_trust_state": state,
            "interpretation_ar": rt.get("interpretation_ar"),
            "replay_reuse_last": rt.get("replay_reuse_last"),
        },
        "workshop_question_id": "replay_trusted",
        "facilitator_verdict": (workshop_q or {}).get("facilitator_verdict"),
        "satisfied": _band_ok(band),
    }


def _review_canonical_drift(stability: Dict[str, Any], workshop_q: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = stability.get("metrics") or {}
    bands = stability.get("health_bands") or {}
    drift_band = (bands.get("canonical_drift_rate") or {}).get("band", "unknown")
    hash_band = (bands.get("hash_divergence_rate") or {}).get("band", "unknown")
    band = "red" if "red" in (drift_band, hash_band) else (
        "amber" if "amber" in (drift_band, hash_band) else "green"
    )
    return {
        "dimension": "canonical_drift",
        "question_ar": "هل انخفض canonical drift؟",
        "auto_band": band,
        "evidence": {
            "canonical_drift_rate": metrics.get("canonical_drift_rate"),
            "hash_divergence_rate": metrics.get("hash_divergence_rate"),
            "overall_stability": stability.get("overall_stability"),
        },
        "workshop_question_id": "canonical_drift_decreased",
        "facilitator_verdict": (workshop_q or {}).get("facilitator_verdict"),
        "satisfied": _band_ok(band),
    }


def _review_l3_confusion(synthesis: Dict[str, Any], workshop_q: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    l3 = synthesis.get("l3_confusion_map") or {}
    manual = int(l3.get("manual_confusion_count") or 0)
    obs_n = int(synthesis.get("observations_count") or 0)
    if obs_n == 0:
        band = "unknown"
    elif manual == 0:
        band = "green"
    elif manual <= max(1, obs_n // 5):
        band = "amber"
    else:
        band = "red"
    return {
        "dimension": "l3_confusion",
        "question_ar": "هل L3 confusion بقي منخفضاً؟",
        "auto_band": band,
        "evidence": {"manual_confusion_count": manual, "observations_count": obs_n},
        "workshop_question_id": "reviewers_understand_l3",
        "facilitator_verdict": (workshop_q or {}).get("facilitator_verdict"),
        "satisfied": band in ("green", "amber") and obs_n > 0,
    }


def _review_unresolved_s5(cohort_metrics: Dict[str, Any], workshop_q: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    max_sev = cohort_metrics.get("cohort_max_severity")
    export_gates = int(cohort_metrics.get("export_review_required_count") or 0)
    has_s5 = max_sev == "S5" or export_gates > 0
    band = "red" if has_s5 else "green"
    return {
        "dimension": "unresolved_s5",
        "question_ar": "هل يوجد unresolved S5؟",
        "auto_band": band,
        "evidence": {
            "cohort_max_severity": max_sev,
            "export_review_required_count": export_gates,
        },
        "workshop_question_id": "no_unresolved_s5",
        "facilitator_verdict": (workshop_q or {}).get("facilitator_verdict"),
        "satisfied": not has_s5,
    }


def _review_modality_dominance(cohort_metrics: Dict[str, Any]) -> Dict[str, Any]:
    counts = cohort_metrics.get("gfm_counts") or {}
    mod = int(counts.get("GFM_MODALITY_DOMINANCE") or 0)
    total = sum(int(v) for v in counts.values()) or 1
    ratio = mod / total
    band = "green" if mod == 0 else ("amber" if ratio < 0.15 else "red")
    return {
        "dimension": "modality_dominance",
        "question_ar": "هل modality dominance تحت السيطرة؟",
        "auto_band": band,
        "evidence": {"GFM_MODALITY_DOMINANCE": mod, "gfm_counts": counts},
        "workshop_question_id": None,
        "facilitator_verdict": None,
        "satisfied": _band_ok(band),
    }


def _review_mitigation(mitigation: Dict[str, Any], workshop_q: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    eff = mitigation.get("overall_effectiveness_rate")
    total = int(mitigation.get("total_records") or 0)
    if total == 0:
        band = "unknown"
    elif eff is not None and eff >= 0.5:
        band = "green"
    elif eff is not None and eff >= 0.25:
        band = "amber"
    else:
        band = "red"
    return {
        "dimension": "mitigation_effectiveness",
        "question_ar": "هل mitigation effectiveness عملت فعلاً؟",
        "auto_band": band,
        "evidence": {
            "total_records": total,
            "overall_effectiveness_rate": eff,
        },
        "workshop_question_id": "mitigation_loops_work",
        "facilitator_verdict": (workshop_q or {}).get("facilitator_verdict"),
        "satisfied": _band_ok(band) if band != "unknown" else False,
    }


def _workshop_by_id(workshop: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {q.get("id"): q for q in (workshop.get("questions") or []) if q.get("id")}


def _step_status(
    step_id: str,
    *,
    workshop: Dict[str, Any],
    gate: Dict[str, Any],
    signed_verdicts: List[Dict[str, Any]],
) -> str:
    if step_id == "epoch_workshop_review":
        reviews = signed_verdicts
        if reviews:
            return "complete"
        if workshop.get("auto_assessment", {}).get("preliminary_ready"):
            return "ready_for_facilitator"
        return "in_progress"
    if step_id == "signed_institutional_verdict":
        if any(r.get("transition_verdict") == VERDICT_ACTIVATES_V2 for r in signed_verdicts):
            return "complete"
        if signed_verdicts:
            return "complete_other_verdict"
        return "blocked"
    if step_id == "governance_freeze_v2":
        return "complete" if gate.get("l4_sandbox_permitted") else "blocked"
    if step_id == "minimal_l4_sandbox":
        return "complete" if gate.get("l4_sandbox_permitted") else "blocked"
    return "blocked"


def build_l4_decision_package(
    db: Any,
    *,
    batch_id: Optional[int] = None,
    assignment_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Full institutional decision package for the L4 transition gate.
    """
    from app.canonical_stability_metrics import compute_canonical_stability_metrics
    from app.governance_drift_monitor import analyze_cohort_governance_metrics
    from app.governance_epoch_narrative import build_epoch_narrative, build_epoch_review_rfc_package
    from app.governance_epoch_workshop import build_epoch_workshop_review, load_epoch_workshop_reviews
    from app.governance_mitigation_memory import analyze_mitigation_effectiveness
    from app.governance_pilot_observatory import load_observations, synthesize_cohort_governance_report

    gate = get_l4_gate_status()
    freeze_report = build_freeze_registry_report()

    workshop = build_epoch_workshop_review(
        db,
        current_epoch_id=ACTIVE_FREEZE_EPOCH,
        target_epoch_id="epoch_2",
        assignment_id=assignment_id,
    )
    wmap = _workshop_by_id(workshop)

    signed_verdicts = load_epoch_workshop_reviews(
        current_epoch_id="epoch_1",
        target_epoch_id="epoch_2",
    )

    narrative = build_epoch_narrative(
        db, epoch_id=ACTIVE_FREEZE_EPOCH, assignment_id=assignment_id
    )
    rfc = build_epoch_review_rfc_package(
        db,
        epoch_id=ACTIVE_FREEZE_EPOCH,
        current_epoch_id=ACTIVE_FREEZE_EPOCH,
        assignment_id=assignment_id,
    )

    try:
        mitigation = analyze_mitigation_effectiveness()
    except Exception:
        mitigation = {}

    stability = compute_canonical_stability_metrics(
        db, batch_id=batch_id, assignment_id=assignment_id
    )

    synthesis: Dict[str, Any] = {}
    cohort_metrics: Dict[str, Any] = {}
    try:
        from app.models import Submission, SubmissionStatus
        import json as _json

        q = db.query(Submission).filter(Submission.status == SubmissionStatus.COMPLETED)
        if batch_id:
            q = q.filter(Submission.batch_id == batch_id)
        if assignment_id:
            q = q.filter(Submission.assignment_id == assignment_id)
        subs = q.limit(100).all()
        snapshots = []
        for sub in subs:
            if sub.grading_snapshot_json:
                try:
                    snapshots.append(_json.loads(str(sub.grading_snapshot_json)))
                except Exception:
                    pass
        if batch_id and snapshots:
            synthesis = synthesize_cohort_governance_report(
                batch_id=batch_id, snapshots=snapshots
            )
        if snapshots:
            cohort_metrics = analyze_cohort_governance_metrics(snapshots)
    except Exception:
        pass

    if not synthesis and batch_id:
        obs = load_observations(batch_id=batch_id)
        synthesis = {
            "observations_count": len(obs),
            "l3_confusion_map": {"manual_confusion_count": sum(
                1 for o in obs
                if (o.get("section_b_reviewer_behaviour") or {}).get("l3_confused_with_verification")
            )},
        }

    from app.facilitator_epistemic_worksheet import synthesize_epistemic_behavioural_evidence

    pilot_obs = load_observations(batch_id=batch_id) if batch_id else load_observations()
    epistemic_evidence = synthesize_epistemic_behavioural_evidence(
        pilot_obs, batch_id=batch_id
    )

    review_table = [
        _review_replay_trust(narrative, wmap.get("replay_trusted")),
        _review_canonical_drift(stability, wmap.get("canonical_drift_decreased")),
        _review_l3_confusion(synthesis, wmap.get("reviewers_understand_l3")),
        _review_unresolved_s5(cohort_metrics, wmap.get("no_unresolved_s5")),
        _review_modality_dominance(cohort_metrics),
        _review_mitigation(mitigation, wmap.get("mitigation_loops_work")),
    ]

    red_count = sum(1 for r in review_table if r.get("auto_band") == "red")
    unknown_count = sum(1 for r in review_table if r.get("auto_band") == "unknown")
    auto_ready = red_count == 0 and unknown_count <= 1

    steps = []
    for s in ORDERED_STEPS:
        steps.append({
            **s,
            "status": _step_status(
                s["id"],
                workshop=workshop,
                gate=gate,
                signed_verdicts=signed_verdicts,
            ),
        })

    current = FREEZE_EPOCHS.get("epoch_1", {})
    target = FREEZE_EPOCHS.get("epoch_2", {})

    return {
        "report_type": "l4_institutional_decision_package",
        "decision_point_id": DECISION_POINT_ID,
        "purpose_ar": (
            "نقطة القرار المؤسسي L4 — did the pilot justify runtime authority expansion؟ "
            "ليس «ابدأ البرمجة مباشرة»."
        ),
        "batch_id": batch_id,
        "assignment_id": assignment_id,
        "current_epoch": {
            "epoch_id": "epoch_1",
            "freeze_id": current.get("freeze_id"),
        },
        "proposed_epoch": {
            "epoch_id": "epoch_2",
            "freeze_id": target.get("freeze_id"),
            "freeze_v2_draft": "app/calibration/GOVERNANCE_FREEZE_v2.md",
        },
        "core_question": "did_the_pilot_justify_runtime_authority_expansion",
        "review_table": review_table,
        "auto_readiness": {
            "red_signals": red_count,
            "unknown_signals": unknown_count,
            "preliminary_ready_for_workshop": auto_ready,
            "note_ar": "auto-prefill ليس verdict — facilitator يوقّع artifact.",
        },
        "ordered_steps": steps,
        "l4_gate": gate,
        "freeze_registry": freeze_report,
        "workshop_review": {
            "url": "/governance-epoch-workshop?target_epoch=epoch_2",
            "api": "/api/governance/epoch/workshop-review",
            "auto_assessment": workshop.get("auto_assessment"),
        },
        "signed_verdicts": [
            {
                "artifact_id": (r.get("signed_institutional_artifact") or {}).get("artifact_id"),
                "transition_verdict": r.get("transition_verdict"),
                "logged_at": r.get("logged_at"),
            }
            for r in signed_verdicts
        ],
        "rfc_package_excerpt": {
            "epoch_id": rfc.get("epoch_id"),
            "rfc_purpose_ar": (rfc.get("rfc_purpose") or {}).get("purpose_ar"),
            "api": f"/api/governance/epoch/epoch_1/rfc-review",
        },
        "confidence_acceleration_warning": {
            "forbidden": True,
            "message_ar": (
                "أخطر خطأ بعد نجاح pilot: confidence acceleration — "
                "«النظام جاهز للتقييم الذاتي الكامل». "
                "pilot يثبت institutional governance stability under controlled ambiguity فقط."
            ),
        },
        "transformation_ar": {
            "from": "evidence-governed assessment",
            "to": "runtime-observable educational assessment",
            "human_rule_ar": "runtime observation remains advisory until human review",
        },
        "epistemic_behavioural_evidence": epistemic_evidence,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
