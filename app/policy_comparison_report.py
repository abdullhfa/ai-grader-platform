"""
Policy Comparison Report — batch-level Governance Impact Analysis.

Consumer of counterfactual replay — descriptive, not normative.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.academic_event_replay import build_academic_timeline_replay
from app.counterfactual_replay import detect_governance_drift
from app.governance_contract_registry import (
    DEFAULT_BASELINE_CONTRACT,
    DEFAULT_COMPARISON_CONTRACT,
    get_contract,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hold_count(state_summary: Dict[str, Any]) -> int:
    n = 0
    for crit in (state_summary.get("criteria") or {}).values():
        if isinstance(crit, dict) and crit.get("status") == "HOLD":
            n += 1
    return n


def _achieved_count(state_summary: Dict[str, Any]) -> int:
    n = 0
    for crit in (state_summary.get("criteria") or {}).values():
        if isinstance(crit, dict) and crit.get("achieved"):
            n += 1
    return n


def _authority_uses_runtime(state_summary: Dict[str, Any]) -> bool:
    gov = state_summary.get("governance") or {}
    if "L4" in str(gov.get("active_authority") or ""):
        return True
    for crit in (state_summary.get("criteria") or {}).values():
        if isinstance(crit, dict) and "RUNTIME" in str(crit.get("achievement_authority") or ""):
            return True
    return False


def analyze_submission_policy_impact(
    submission,
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
    graded_at: Optional[str] = None,
) -> Dict[str, Any]:
    raw = getattr(submission, "grading_snapshot_json", None)
    sid = getattr(submission, "id", None)
    name = getattr(submission, "student_name", "") or ""
    if not raw:
        return {"submission_id": sid, "student_name": name, "skipped": True}

    try:
        snap = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {"submission_id": sid, "student_name": name, "skipped": True}

    timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
    events = timeline.get("events") or []
    if not events:
        return {"submission_id": sid, "student_name": name, "skipped": True}

    ctx = {
        "evidence_lineage": (
            (snap.get("explainability_layer") or {}).get("evidence_lineage")
            or snap.get("evidence_lineage")
        ),
    }
    report = detect_governance_drift(
        events,
        baseline_contract=baseline_contract,
        comparison_contract=comparison_contract,
        sandbox_context=ctx,
    )
    drift = report.get("drift") or {}
    base = report.get("baseline_state_summary") or {}
    comp = report.get("comparison_state_summary") or {}

    low_conf_achieved = False
    for item in drift.get("drift_items") or []:
        diff = item.get("diff") or {}
        if diff.get("comparison_achieved") and diff.get("comparison_confidence") is not None:
            if float(diff["comparison_confidence"]) < 0.55:
                low_conf_achieved = True

    return {
        "submission_id": sid,
        "student_name": name,
        "skipped": False,
        "counterfactual": True,
        "drift_detected": drift.get("drift_detected"),
        "drift_count": drift.get("drift_count"),
        "drift_items": drift.get("drift_items") or [],
        "drift_provenance": drift.get("drift_provenance") or [],
        "baseline_hold_count": _hold_count(base),
        "comparison_hold_count": _hold_count(comp),
        "baseline_achieved_count": _achieved_count(base),
        "comparison_achieved_count": _achieved_count(comp),
        "baseline_runtime_authority": _authority_uses_runtime(base),
        "comparison_runtime_authority": _authority_uses_runtime(comp),
        "low_confidence_achieved_risk": low_conf_achieved,
        "authority_shift": any(i.get("authority_shift") for i in (drift.get("drift_items") or [])),
    }


def build_batch_policy_comparison_report(
    db,
    batch_id: int,
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
) -> Dict[str, Any]:
    """
    Governance Impact Analysis — batch counterfactual policy comparison.
    Descriptive only; does not mutate submissions.
    """
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )

    rows: List[Dict[str, Any]] = []
    provenance_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    scope_counter: Counter[str] = Counter()

    baseline_holds = 0
    comparison_holds = 0
    baseline_achieved = 0
    comparison_achieved = 0
    drift_submissions = 0
    authority_shifts = 0
    runtime_reliance_b = 0
    runtime_reliance_c = 0
    low_conf_risk = 0
    human_review_baseline = 0

    for sub in subs:
        graded_at = None
        if getattr(sub, "summary", None) and sub.summary.graded_at:
            graded_at = sub.summary.graded_at.isoformat() + "Z"
        row = analyze_submission_policy_impact(
            sub,
            baseline_contract=baseline_contract,
            comparison_contract=comparison_contract,
            graded_at=graded_at,
        )
        rows.append(row)
        if row.get("skipped"):
            continue

        baseline_holds += row.get("baseline_hold_count") or 0
        comparison_holds += row.get("comparison_hold_count") or 0
        baseline_achieved += row.get("baseline_achieved_count") or 0
        comparison_achieved += row.get("comparison_achieved_count") or 0
        if row.get("drift_detected"):
            drift_submissions += 1
        if row.get("authority_shift"):
            authority_shifts += 1
        if row.get("baseline_runtime_authority"):
            runtime_reliance_b += 1
        if row.get("comparison_runtime_authority"):
            runtime_reliance_c += 1
        if row.get("low_confidence_achieved_risk"):
            low_conf_risk += 1
        if (row.get("baseline_hold_count") or 0) > 0:
            human_review_baseline += 1

        for p in row.get("drift_provenance") or []:
            provenance_counter[p.get("code") or "unknown"] += 1
        for item in row.get("drift_items") or []:
            severity_counter[item.get("severity") or "unknown"] += 1
            scope_counter[item.get("drift_scope") or "unknown"] += 1

    analyzed = [r for r in rows if not r.get("skipped")]
    n = len(analyzed) or 1

    hold_reduction = baseline_holds - comparison_holds
    hold_reduction_rate = round(hold_reduction / max(baseline_holds, 1), 4)

    runtime_reliance_delta = runtime_reliance_c - runtime_reliance_b
    runtime_reliance_change_rate = round(runtime_reliance_delta / n, 4)

    human_review_reduction = human_review_baseline - sum(
        1 for r in analyzed if (r.get("comparison_hold_count") or 0) > 0
    )
    human_review_reduction_rate = round(human_review_reduction / max(human_review_baseline, 1), 4)

    false_confidence_rate = round(low_conf_risk / n, 4)

    report_id = f"pcr_{uuid.uuid4().hex[:16]}"
    body_core = {
        "report_id": report_id,
        "batch_id": batch_id,
        "baseline_contract": baseline_contract,
        "comparison_contract": comparison_contract,
        "submissions_analyzed": len(analyzed),
        "counterfactual": True,
    }
    report = {
        **body_core,
        "schema": "1.0",
        "mode": "policy_comparison_governance_impact",
        "generated_at": _utc_now_iso(),
        "counterfactual": True,
        "contracts": {
            "baseline": get_contract(baseline_contract),
            "comparison": get_contract(comparison_contract),
        },
        "impact_analysis": {
            "hold_reduction": hold_reduction,
            "hold_reduction_rate": hold_reduction_rate,
            "baseline_hold_total": baseline_holds,
            "comparison_hold_total": comparison_holds,
            "achieved_delta": comparison_achieved - baseline_achieved,
            "authority_shift_submissions": authority_shifts,
            "authority_shift_rate": round(authority_shifts / n, 4),
            "runtime_reliance_baseline": runtime_reliance_b,
            "runtime_reliance_comparison": runtime_reliance_c,
            "runtime_reliance_change_rate": runtime_reliance_change_rate,
            "human_review_reduction": human_review_reduction,
            "human_review_reduction_rate": human_review_reduction_rate,
            "false_confidence_risk_submissions": low_conf_risk,
            "false_confidence_risk_rate": false_confidence_rate,
            "drift_submissions": drift_submissions,
            "drift_rate": round(drift_submissions / n, 4),
        },
        "drift_provenance_aggregate": [
            {"code": k, "count": v} for k, v in provenance_counter.most_common()
        ],
        "severity_distribution": [
            {"severity": k, "count": v} for k, v in severity_counter.most_common()
        ],
        "drift_scope_distribution": [
            {"drift_scope": k, "count": v} for k, v in scope_counter.most_common()
        ],
        "disclaimer_ar": (
            "تحليل تأثير سياسة — counterfactual وصفي. "
            "يصف اختلاف outcomes تحت عقود مختلفة — لا يُقيّم «أفضلية» أو عدالة."
        ),
        "disclaimer_en": (
            "Policy impact analysis — descriptive counterfactual. "
            "Reports outcome differences under contracts — not which is «better»."
        ),
        "normative_boundary_ar": "وصفي — ليس normative fairness verdict",
        "rows": rows,
        "report_hash": "",
    }
    hash_body = {k: v for k, v in report.items() if k != "report_hash" and k != "rows"}
    report["report_hash"] = hashlib.sha256(_stable_json(hash_body).encode("utf-8")).hexdigest()
    return report
