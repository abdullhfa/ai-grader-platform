"""
Governance Epoch Workshop Review — institutional (not technical) gate before freeze evolution.

Facilitator-led workshop answers six governance questions before any
GOVERNANCE_FREEZE_v2 transition.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import ACTIVE_FREEZE_EPOCH, FREEZE_EPOCHS
from app.governance_epoch_narrative import (
    _aggregate_history_metrics,
    _collect_transition_events,
    _replay_trust_interpretation,
    build_epoch_narrative,
)
from app.governance_pilot_observatory import load_observations

WORKSHOP_VERSION = "EPOCH_WORKSHOP_REVIEW_v1"
WORKSHOP_DIR = Path("app/calibration/human_cohort_workshop")
REVIEWS_FILE = "epoch_workshop_reviews.jsonl"

EPOCH_WORKSHOP_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "replay_trusted",
        "question_ar": "هل replay أصبح trusted؟",
        "rationale_ar": "provenance legitimacy",
        "not_technical_ar": "ليس: هل الAPI يعمل — بل: هل المراجعون يثقون بالـ canonical replay",
    },
    {
        "id": "authority_boundaries_stable",
        "question_ar": "هل authority boundaries مستقرة؟",
        "rationale_ar": "semantic containment",
        "not_technical_ar": "ليس: هل prompts محدّثة — بل: هل L1–L3 لا تتسرّب كـ verification",
    },
    {
        "id": "mitigation_loops_work",
        "question_ar": "هل mitigation loops تعمل؟",
        "rationale_ar": "self-correction health",
        "not_technical_ar": "ليس: هل أُصلح bug — بل: هل النظام يصحّح drift institutionally",
    },
    {
        "id": "canonical_drift_decreased",
        "question_ar": "هل canonical drift انخفض؟",
        "rationale_ar": "reproducibility",
        "not_technical_ar": "ليس: هل accuracy تحسّنت — بل: identical evidence → stable outcomes",
    },
    {
        "id": "reviewers_understand_l3",
        "question_ar": "هل reviewers فهموا L3؟",
        "rationale_ar": "modality containment",
        "not_technical_ar": "ليس: هل شرحنا L3 — بل: هل workshop أظهر confusion = 0",
    },
    {
        "id": "no_unresolved_s5",
        "question_ar": "هل unresolved S5 موجود؟",
        "rationale_ar": "deployment risk",
        "not_technical_ar": "أي S5 drift silence = deployment risk — يجب = لا",
    },
]


def _ensure_dir() -> Path:
    WORKSHOP_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSHOP_DIR


def _read_reviews() -> List[Dict[str, Any]]:
    path = WORKSHOP_DIR / REVIEWS_FILE
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _signal_band(auto: str) -> str:
    return auto if auto in ("green", "amber", "red", "unknown") else "unknown"


def _prefill_question(
    qid: str,
    *,
    agg: Dict[str, Any],
    replay_trust: Dict[str, Any],
    mitigation: Dict[str, Any],
    observations: List[Dict[str, Any]],
    transitions: List[Dict[str, Any]],
    cohort_max_severity: Optional[str],
    export_review_count: int,
) -> Dict[str, Any]:
    """Auto-prefill institutional signals — facilitator confirms in workshop."""
    evidence: List[str] = []
    auto_signal = "unknown"
    workshop_prompt_ar = ""

    if qid == "replay_trusted":
        state = replay_trust.get("state", "unknown")
        replay_last = replay_trust.get("replay_reuse_last")
        if state == "canonical_trusted":
            auto_signal = "green"
        elif state in ("provenance_abandonment_risk", "canonical_legitimacy_pressure"):
            auto_signal = "red"
        elif state == "governance_stabilizing":
            auto_signal = "amber"
        evidence.append(replay_trust.get("interpretation_ar", ""))
        if replay_last is not None:
            evidence.append(f"replay_reuse_rate الأخير: {replay_last}")
        workshop_prompt_ar = "ناقش: هل reviewers يفتحون replay ويتبعون canonical؟"

    elif qid == "authority_boundaries_stable":
        freeze_trend = agg.get("governance_clean_trend", "insufficient_data")
        if freeze_trend == "improving":
            auto_signal = "green"
        elif freeze_trend == "stable" and agg.get("readings", 0) >= 2:
            auto_signal = "amber"
        elif freeze_trend == "degrading":
            auto_signal = "red"
        evidence.append(f"governance_clean_ratio trend: {freeze_trend}")
        if cohort_max_severity in ("S4", "S5"):
            evidence.append(f"cohort max severity: {cohort_max_severity}")
            auto_signal = "red" if cohort_max_severity == "S5" else auto_signal
        workshop_prompt_ar = "ناقش: semantic escalation / authority inflation في workshop"

    elif qid == "mitigation_loops_work":
        total = mitigation.get("total_records", 0)
        eff = mitigation.get("overall_effectiveness_rate")
        if total == 0:
            auto_signal = "unknown"
            evidence.append("لا سجلات mitigation بعد")
        elif eff is not None and eff >= 0.5:
            auto_signal = "green"
        elif eff is not None and eff >= 0.25:
            auto_signal = "amber"
        else:
            auto_signal = "red"
        evidence.append(f"mitigation records: {total}, effectiveness: {eff}")
        workshop_prompt_ar = "ناقش: هل mitigations أُ Applied بعد drift incidents؟"

    elif qid == "canonical_drift_decreased":
        drift_trend = agg.get("canonical_drift_trend", "insufficient_data")
        hash_trend = agg.get("hash_divergence_trend", "insufficient_data")
        if drift_trend == "improving" and hash_trend in ("improving", "stable"):
            auto_signal = "green"
        elif drift_trend == "stable":
            auto_signal = "amber"
        elif drift_trend == "degrading" or hash_trend == "degrading":
            auto_signal = "red"
        evidence.append(f"canonical_drift trend: {drift_trend}")
        evidence.append(f"hash_divergence trend: {hash_trend}")
        if any(e.get("event") == "hash_divergence_spike" for e in transitions[-5:]):
            auto_signal = "red"
            evidence.append("hash_divergence_spike في readings الأخيرة")
        workshop_prompt_ar = "ناقش: حالة احمد P/D — هل supersession policy كافية؟"

    elif qid == "reviewers_understand_l3":
        obs_n = len(observations)
        l3_conf = sum(
            1 for o in observations
            if (o.get("section_b_reviewer_behaviour") or {}).get("l3_confused_with_verification")
        )
        if obs_n == 0:
            auto_signal = "unknown"
            evidence.append("لا observations مسجّلة — أجرِ cohort workshop أولاً")
        elif l3_conf == 0:
            auto_signal = "green"
        elif l3_conf <= obs_n * 0.2:
            auto_signal = "amber"
        else:
            auto_signal = "red"
        evidence.append(f"L3 confusion: {l3_conf} / {obs_n} observations")
        workshop_prompt_ar = "ناقش: replay + L3 advisory — هل confusion = 0؟"

    elif qid == "no_unresolved_s5":
        has_s5 = cohort_max_severity == "S5"
        if has_s5 or export_review_count > 0:
            auto_signal = "red"
            evidence.append(f"cohort_max_severity={cohort_max_severity}, export_gates={export_review_count}")
        elif cohort_max_severity in (None, "S1", "S2", "S3", "S4"):
            auto_signal = "green" if cohort_max_severity in ("S1", "S2", "S3") else "amber"
            evidence.append(f"cohort_max_severity={cohort_max_severity or 'unknown'}")
        workshop_prompt_ar = "يجب أن تكون الإجابة: لا S5 unresolved — وإلا لا transition"

    base = next(q for q in EPOCH_WORKSHOP_QUESTIONS if q["id"] == qid)
    return {
        **base,
        "auto_signal": _signal_band(auto_signal),
        "auto_evidence_ar": [e for e in evidence if e],
        "workshop_prompt_ar": workshop_prompt_ar,
        "facilitator_verdict": None,
        "facilitator_notes_ar": "",
    }


def build_epoch_workshop_review(
    db: Any,
    *,
    current_epoch_id: str = ACTIVE_FREEZE_EPOCH,
    target_epoch_id: str = "epoch_2",
    assignment_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Draft epoch workshop review — auto-prefill + facilitator completion."""
    from app.canonical_stability_trajectory import load_stability_history
    from app.governance_drift_monitor import analyze_cohort_governance_metrics
    from app.governance_mitigation_memory import analyze_mitigation_effectiveness

    current = FREEZE_EPOCHS.get(current_epoch_id, {})
    target = FREEZE_EPOCHS.get(target_epoch_id, {})

    history = load_stability_history(
        assignment_id=assignment_id,
        freeze_epoch=current_epoch_id,
        limit=200,
    )
    agg = _aggregate_history_metrics(history)
    transitions = _collect_transition_events(history)
    narrative = build_epoch_narrative(
        db, epoch_id=current_epoch_id, assignment_id=assignment_id
    )
    replay_trust = narrative.get("replay_trust_state") or {}

    try:
        mitigation = analyze_mitigation_effectiveness()
    except Exception:
        mitigation = {}

    observations = load_observations()

    cohort_metrics: Dict[str, Any] = {}
    try:
        from app.models import Submission, SubmissionStatus
        subs = db.query(Submission).filter(Submission.status == SubmissionStatus.COMPLETED)
        if assignment_id:
            subs = subs.filter(Submission.assignment_id == assignment_id)
        snapshots = []
        for sub in subs.limit(100).all():
            if sub.grading_snapshot_json:
                try:
                    snapshots.append(json.loads(str(sub.grading_snapshot_json)))
                except Exception:
                    pass
        if snapshots:
            cohort_metrics = analyze_cohort_governance_metrics(snapshots)
    except Exception:
        cohort_metrics = {}

    cohort_max = cohort_metrics.get("cohort_max_severity")
    export_review = int(cohort_metrics.get("export_review_required_count") or 0)

    questions = [
        _prefill_question(
            q["id"],
            agg=agg,
            replay_trust=replay_trust,
            mitigation=mitigation,
            observations=observations,
            transitions=transitions,
            cohort_max_severity=cohort_max,
            export_review_count=export_review,
        )
        for q in EPOCH_WORKSHOP_QUESTIONS
    ]

    auto_red = sum(1 for q in questions if q["auto_signal"] == "red")
    auto_unknown = sum(1 for q in questions if q["auto_signal"] == "unknown")

    return {
        "report_type": "epoch_workshop_review",
        "workshop_version": WORKSHOP_VERSION,
        "not": "technical review",
        "purpose_ar": (
            "ورشة epoch review مؤسسية — قبل GOVERNANCE_FREEZE_v2 — "
            "epoch transition justified institutionally."
        ),
        "current_epoch": {
            "epoch_id": current_epoch_id,
            "freeze_id": current.get("freeze_id"),
            "label_ar": current.get("label_ar"),
        },
        "proposed_epoch": {
            "epoch_id": target_epoch_id,
            "freeze_id": target.get("freeze_id"),
            "label_ar": target.get("label_ar"),
            "status": target.get("status"),
        },
        "assignment_id": assignment_id,
        "questions": questions,
        "auto_assessment": {
            "red_signals": auto_red,
            "unknown_signals": auto_unknown,
            "workshop_required_ar": (
                "أكمل الورشة مع facilitators — auto-prefill ليس verdict نهائي."
            ),
            "preliminary_ready": auto_red == 0 and auto_unknown <= 1,
        },
        "epoch_narrative_excerpt": (narrative.get("narrative_ar") or [])[:6],
        "transition_verdict": None,
        "transition_verdict_options": [
            "epoch_transition_justified_institutionally",
            "not_yet_requires_mitigation",
            "defer_until_cohort_workshop_complete",
        ],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def save_epoch_workshop_review(record: Dict[str, Any]) -> Dict[str, Any]:
    """Persist completed facilitator epoch workshop review as signed institutional artifact."""
    from app.institutional_artifact import sign_institutional_artifact

    _ensure_dir()
    path = WORKSHOP_DIR / REVIEWS_FILE
    now = datetime.datetime.utcnow().isoformat() + "Z"

    signatory_name = str(record.get("facilitator") or record.get("signatory_name") or "").strip()
    signatory_role = str(record.get("signatory_role") or "governance_facilitator").strip()
    institution_affirmation = bool(record.get("institution_affirmation"))

    current_epoch = record.get("current_epoch") or {}
    proposed_epoch = record.get("proposed_epoch") or {}
    epoch_id = str(current_epoch.get("epoch_id") or "")

    ledger_refs = list(record.get("ledger_entry_ids") or [])
    if not ledger_refs and epoch_id:
        try:
            from app.governance_epoch_mitigation_ledger import load_ledger_entries

            ledger_refs = [
                e.get("entry_id")
                for e in load_ledger_entries(epoch_id=epoch_id)
                if e.get("entry_id")
            ]
        except Exception:
            ledger_refs = []

    artifact_body = {
        "workshop_version": record.get("workshop_version") or WORKSHOP_VERSION,
        "current_epoch": current_epoch,
        "proposed_epoch": proposed_epoch,
        "assignment_id": record.get("assignment_id"),
        "transition_verdict": record.get("transition_verdict"),
        "question_verdicts": record.get("question_verdicts") or [],
        "workshop_notes_ar": record.get("workshop_notes_ar") or "",
    }

    signed_artifact = sign_institutional_artifact(
        artifact_body,
        artifact_kind="epoch_workshop_verdict",
        signatory_name=signatory_name,
        signatory_role=signatory_role,
        institution_affirmation=institution_affirmation,
        freeze_epoch_id=str(current_epoch.get("epoch_id") or ""),
        freeze_id=str(current_epoch.get("freeze_id") or ""),
        provenance_refs=ledger_refs + list(record.get("provenance_refs") or []),
    )

    out = {
        **record,
        "workshop_version": record.get("workshop_version") or WORKSHOP_VERSION,
        "logged_at": now,
        "source": "epoch_workshop_review",
        "signed_institutional_artifact": {
            "artifact_id": signed_artifact["artifact_id"],
            "content_hash": signed_artifact["content_hash"],
            "signed_at": signed_artifact["signed_at"],
            "signatory": signed_artifact["signatory"],
            "artifact_path": f"app/calibration/institutional_artifacts/{signed_artifact['artifact_id']}.json",
        },
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")

    activation: Dict[str, Any] = {"activated": False}
    verdict = str(record.get("transition_verdict") or "")
    proposed_epoch_id = str((proposed_epoch or {}).get("epoch_id") or "epoch_2")
    if verdict == "epoch_transition_justified_institutionally":
        from app.governance_freeze_registry import activate_freeze_epoch_from_verdict

        activation = activate_freeze_epoch_from_verdict(
            target_epoch_id=proposed_epoch_id,
            artifact_id=signed_artifact["artifact_id"],
            transition_verdict=verdict,
        )

    return {
        "ok": True,
        "log_path": str(path),
        "logged_at": now,
        "artifact_id": signed_artifact["artifact_id"],
        "content_hash": signed_artifact["content_hash"],
        "signed_institutional_artifact": True,
        "freeze_epoch_activation": activation,
    }


def load_epoch_workshop_reviews(
    *,
    current_epoch_id: Optional[str] = None,
    target_epoch_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows = _read_reviews()
    if current_epoch_id:
        rows = [
            r for r in rows
            if (r.get("current_epoch") or {}).get("epoch_id") == current_epoch_id
        ]
    if target_epoch_id:
        rows = [
            r for r in rows
            if (r.get("proposed_epoch") or {}).get("epoch_id") == target_epoch_id
        ]
    return rows
