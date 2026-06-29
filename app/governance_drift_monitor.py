"""
Governance Drift Monitor — semantic drift detection against GOVERNANCE_FREEZE_v1.

Detects silent authority inflation: stronger language, missing downgrades,
invisible contradictions, replay/provenance gaps.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.evidence_authority_mapping import (
    FORBIDDEN_CLAIM_PATTERNS,
    check_claim_authority,
)

FREEZE_ID = "GOVERNANCE_FREEZE_v1"
FREEZE_JSON_PATH = Path(__file__).resolve().parent / "calibration" / "GOVERNANCE_FREEZE_v1.json"

# Stronger-language drift patterns (beyond forbidden — watch list)
_DRIFT_WATCH_PATTERNS: List[tuple[str, str]] = [
    (r"\bfully\s+verified\b", "strong_verification_language"),
    (r"\bconfirmed\s+working\b", "confirmed_working"),
    (r"\bdefinitely\s+achieved\b", "definite_achievement_claim"),
    (r"\bwithout\s+doubt\b", "certainty_language"),
    (r"مؤكد\s+تماماً", "ar_certainty_language"),
    (r"يعمل\s+بشكل\s+ممتاز", "ar_game_works_praise"),
    (r"\bL3\b.*\bverif", "l3_confused_with_verification"),
]


def _load_freeze() -> Dict[str, Any]:
    try:
        with open(FREEZE_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"id": FREEZE_ID, "max_auto_runtime_level": 3}


def scan_text_for_drift(text: str) -> List[Dict[str, str]]:
    """Return drift watch signals in arbitrary text."""
    if not text or not text.strip():
        return []
    signals: List[Dict[str, str]] = []
    for pattern, code in _DRIFT_WATCH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            signals.append({"code": code, "pattern": pattern})
    auth = check_claim_authority(text)
    for v in auth.get("violations") or []:
        signals.append({
            "code": "forbidden_claim_drift",
            "detail": v.get("phrase") or v.get("type", ""),
        })
    return signals


def analyze_submission_governance_drift(
    grading_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analyze one submission snapshot against GOVERNANCE_FREEZE_v1.
    Read-only — does not mutate grades.
    """
    snap = grading_snapshot or {}
    freeze = _load_freeze()
    drift_signals: List[Dict[str, Any]] = []
    checks_passed: List[str] = []

    inv = snap.get("artifact_inventory") or {}
    rt_level = (inv.get("runtime_evidence_level") or {}).get("level", 0)
    max_auto = int(freeze.get("max_auto_runtime_level") or 3)

    # ── Check 1: authority level ceiling ──
    if rt_level > max_auto:
        drift_signals.append({
            "severity": "high",
            "code": "runtime_level_exceeds_freeze_ceiling",
            "message_ar": f"runtime_evidence_level L{rt_level} يتجاوز max_auto L{max_auto}.",
        })
    else:
        checks_passed.append("runtime_level_within_ceiling")

    # ── Check 2: L4/L5 not auto-assigned ──
    if rt_level >= 4:
        drift_signals.append({
            "severity": "critical",
            "code": "reserved_level_auto_assigned",
            "message_ar": "L4/L5 محجوز — لا يجب assign آلياً.",
        })

    # ── Check 3: claim language in criteria ──
    overclaim_count = 0
    for cr in snap.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        blob = " ".join(
            str(cr.get(k) or "")
            for k in ("reasoning", "feedback", "overall_feedback")
        )
        for sig in scan_text_for_drift(blob):
            overclaim_count += 1
            drift_signals.append({
                "severity": "medium",
                "code": sig.get("code", "language_drift"),
                "criterion": cr.get("criteria_level"),
                "message_ar": f"language drift في criterion feedback: {sig.get('code')}",
            })

    if overclaim_count == 0:
        checks_passed.append("criterion_language_no_forbidden_drift")

    # ── Check 4: overall feedback ──
    ofb = str(snap.get("overall_feedback") or "")
    for sig in scan_text_for_drift(ofb):
        drift_signals.append({
            "severity": "medium",
            "code": sig.get("code", "overall_feedback_drift"),
            "message_ar": "language drift في overall_feedback",
        })

    # ── Check 5: contradictions visible in inventory ──
    tc = inv.get("temporal_consistency") or {}
    cross = inv.get("cross_artifact_consistency") or {}
    has_contra = bool(tc.get("temporal_consistency_signals") or cross.get("ambiguities"))
    claim_flags = snap.get("claim_authority_flags") or {}
    flags_in_snap = bool(
        (isinstance(claim_flags, dict) and (
            claim_flags.get("temporal_consistency") or claim_flags.get("overclaims")
        ))
        or (isinstance(claim_flags, list) and claim_flags)
    )

    if has_contra and not flags_in_snap:
        drift_signals.append({
            "severity": "medium",
            "code": "contradictions_not_in_claim_flags",
            "message_ar": "تعارضات في inventory لكن claim_authority_flags فارغ — replay gap.",
        })
    elif has_contra and flags_in_snap:
        checks_passed.append("contradictions_surfaced_in_flags")

    # ── Check 6: provenance / replay present when governance artifacts exist ──
    has_gov_artifacts = bool(
        inv.get("authority_mapping")
        or inv.get("evidence_trace_graph")
        or inv.get("gameplay_video_inference", {}).get("videos_analyzed")
    )
    has_replay = bool(snap.get("authority_replay") or inv.get("evidence_trace_graph"))
    if has_gov_artifacts and not has_replay:
        drift_signals.append({
            "severity": "low",
            "code": "provenance_replay_missing",
            "message_ar": "artifacts governance موجودة لكن authority_replay/graph ناقص.",
        })
    elif has_gov_artifacts:
        checks_passed.append("provenance_present")

    # ── Check 7: downgrade semantics — high contradiction without temporal in replay ──
    replay = snap.get("authority_replay") or {}
    replay_steps = replay.get("steps") or []
    has_contra_step = any(s.get("phase") == "contradiction" for s in replay_steps)
    if has_contra and replay_steps and not has_contra_step:
        drift_signals.append({
            "severity": "medium",
            "code": "replay_ignores_contradiction",
            "message_ar": "contradictions في inventory لكن replay لا يعرض downgrade steps.",
        })
    elif has_contra and has_contra_step:
        checks_passed.append("replay_shows_downgrade")

    # ── Check 7b: runtime claims contract (L0–L3 constitutional envelope) ──
    registry = inv.get("runtime_claims_registry") or {}
    if has_gov_artifacts or registry.get("claim_count"):
        if not registry.get("claims"):
            drift_signals.append({
                "severity": "medium",
                "code": "runtime_claims_registry_missing",
                "message_ar": "runtime artifacts موجودة لكن runtime_claims_registry فارغ.",
            })
        elif not registry.get("contract_complete"):
            drift_signals.append({
                "severity": "high",
                "code": "runtime_claim_contract_incomplete",
                "message_ar": "claims registry ناقص — authority/ambiguity/boundary fields missing.",
                "violations": registry.get("violations") or [],
            })
        else:
            checks_passed.append("runtime_claim_contract_complete")
        l2l3 = inv.get("l2_l3_corroborative_runtime") or {}
        if l2l3.get("criterion_authority_auto_inferred"):
            drift_signals.append({
                "severity": "critical",
                "code": "l2_l3_authority_auto_inferred",
                "message_ar": "L2/L3 block يدّعي criterion authority — authority inflation.",
            })

    # ── Check 8: coverage notice when executables present ──
    exec_status = (inv.get("executable_artifacts") or {}).get("status")
    coverage = snap.get("grading_coverage_notice")
    if exec_status == "detected_not_executed" and not coverage:
        drift_signals.append({
            "severity": "medium",
            "code": "executable_present_no_coverage_notice",
            "message_ar": "executables مُرصدَة لكن grading_coverage_notice غائب.",
        })

    severity_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    worst = max(
        (severity_rank.get(s.get("severity", "low"), 0) for s in drift_signals),
        default=0,
    )
    status = "clean" if not drift_signals else (
        "critical_drift" if worst >= 3 else "high_drift" if worst >= 2 else "drift_detected"
    )

    report = {
        "version": 1,
        "freeze_id": FREEZE_ID,
        "status": status,
        "drift_signal_count": len(drift_signals),
        "checks_passed": checks_passed,
        "drift_signals": drift_signals,
        "summary_ar": (
            "لا drift — متوافق مع GOVERNANCE_FREEZE_v1"
            if not drift_signals
            else f"رُصد {len(drift_signals)} إشارة semantic drift — راجع قبل escalation."
        ),
    }

    try:
        from app.governance_failure_taxonomy import enrich_drift_report

        report = enrich_drift_report(report)
    except Exception:
        pass

    try:
        from app.governance_response_protocols import enrich_drift_with_responses

        report = enrich_drift_with_responses(report)
    except Exception:
        pass

    return report


def analyze_cohort_governance_metrics(
    snapshots: List[Dict[str, Any]],
    *,
    cohort_id: str = "pilot_v1",
) -> Dict[str, Any]:
    """
    Aggregate governance metrics for human cohort pilot instrumentation.
    Tests governance freeze under disagreement — not AI accuracy.
    """
    n = len(snapshots)
    if n == 0:
        return {"cohort_id": cohort_id, "submission_count": 0, "metrics": {}}

    per_sub: List[Dict[str, Any]] = []
    replay_present = 0
    drift_any = 0
    overclaim_any = 0
    contra_visible = 0
    l3_present = 0
    l3_verification_confusion = 0
    hold_signals = 0

    for snap in snapshots:
        drift = analyze_submission_governance_drift(snap)
        per_sub.append(drift)
        if drift.get("drift_signal_count", 0) > 0:
            drift_any += 1
        if snap.get("authority_replay") or (snap.get("artifact_inventory") or {}).get("evidence_trace_graph"):
            replay_present += 1
        flags = snap.get("claim_authority_flags") or {}
        if isinstance(flags, dict) and (flags.get("overclaims") or flags.get("temporal_consistency")):
            overclaim_any += 1
        inv = snap.get("artifact_inventory") or {}
        tc = inv.get("temporal_consistency") or {}
        cross = inv.get("cross_artifact_consistency") or {}
        if tc.get("temporal_consistency_signals") or cross.get("ambiguities"):
            contra_visible += 1
        rt = (inv.get("runtime_evidence_level") or {}).get("level", 0)
        if rt >= 3:
            l3_present += 1
        blob = json.dumps(snap, ensure_ascii=False)[:8000]
        if re.search(r"L3.*verif|gameplay verified", blob, re.I):
            l3_verification_confusion += 1
        for sig in drift.get("drift_signals") or []:
            if "hold" in str(sig.get("code", "")).lower():
                hold_signals += 1

    metrics = {
        "replay_presence_rate": round(replay_present / n, 3),
        "drift_detection_rate": round(drift_any / n, 3),
        "claim_flag_surface_rate": round(overclaim_any / n, 3),
        "contradiction_visibility_rate": round(contra_visible / n, 3),
        "l3_submission_rate": round(l3_present / n, 3),
        "l3_verification_confusion_rate": round(l3_verification_confusion / n, 3),
        "hold_signal_count": hold_signals,
        "clean_submission_rate": round(
            sum(1 for d in per_sub if d.get("status") == "clean") / n, 3
        ),
    }

    all_classified: List[Dict[str, Any]] = []
    for d in per_sub:
        for sig in d.get("drift_signals") or []:
            if sig.get("failure_mode_id"):
                all_classified.append(sig)
    failure_taxonomy_agg: Dict[str, Any] = {}
    max_severity_overall = "S1"
    severity_order = ["S1", "S2", "S3", "S4", "S5"]
    export_blocked_count = 0
    try:
        from app.governance_failure_taxonomy import aggregate_failure_modes

        failure_taxonomy_agg = aggregate_failure_modes(all_classified)
    except Exception:
        pass

    for d in per_sub:
        gr = d.get("governance_responses") or {}
        ms = gr.get("max_severity") or "S1"
        if severity_order.index(ms) > severity_order.index(max_severity_overall):
            max_severity_overall = ms
        ep = gr.get("export_policy") or {}
        if not ep.get("allow_export", True):
            export_blocked_count += 1

    base_report = {
        "version": 1,
        "cohort_id": cohort_id,
        "submission_count": n,
        "governance_freeze": FREEZE_ID,
        "purpose_ar": (
            "قياس governance freeze تحت disagreement بشري — "
            "ليس accuracy validation."
        ),
        "metrics": metrics,
        "failure_taxonomy": failure_taxonomy_agg,
        "cohort_max_severity": max_severity_overall,
        "export_review_required_count": export_blocked_count,
        "metric_definitions": {
            "replay_presence_rate": "نسبة التسليمات ذات authority_replay/graph",
            "drift_detection_rate": "نسبة التسليمات ذات semantic drift signals",
            "claim_flag_surface_rate": "نسبة claim_authority_flags المُصدَرة",
            "contradiction_visibility_rate": "نسبة contradictions الظاهرة في inventory",
            "l3_verification_confusion_rate": "مراجع/نص يخلط L3 مع verification",
            "clean_submission_rate": "متوافق تماماً مع freeze",
        },
        "per_submission_drift": per_sub,
    }

    try:
        from app.governance_mitigation_memory import attach_mitigation_memory_to_cohort

        return attach_mitigation_memory_to_cohort(base_report)
    except Exception:
        return base_report
