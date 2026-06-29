"""
Canonical Stability Metrics — institutional reproducibility health over time.

Measures epistemic version-control health: drift, supersession, replay reuse,
reviewer override pressure, and freeze compatibility — not AI accuracy.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.grading_snapshot_governance import (
    TAXONOMY_DRIFT_MODE,
    load_submission_governance_record,
    parse_snapshot_governance,
)
from app.governance_drift_monitor import analyze_submission_governance_drift
from app.governance_failure_taxonomy import classify_drift_signal

METRICS_VERSION = "canonical_stability_v1"


def _safe_ratio(num: int, denom: int) -> Optional[float]:
    if denom <= 0:
        return None
    return round(num / denom, 4)


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _health_band(metric: str, value: Optional[float]) -> str:
    """green / amber / red — institutional stability bands (pilot defaults)."""
    if value is None:
        return "unknown"
    if metric == "governance_clean_ratio":
        if value >= 0.85:
            return "green"
        if value >= 0.6:
            return "amber"
        return "red"
    if metric == "canonical_drift_rate":
        if value <= 0.05:
            return "green"
        if value <= 0.15:
            return "amber"
        return "red"
    if metric == "supersession_frequency":
        if value <= 0.1:
            return "green"
        if value <= 0.25:
            return "amber"
        return "red"
    if metric == "replay_reuse_rate":
        if value >= 0.2:
            return "green"
        if value >= 0.05:
            return "amber"
        return "red"
    if metric == "override_after_canonical_rate":
        if value <= 0.1:
            return "green"
        if value <= 0.3:
            return "amber"
        return "red"
    if metric == "freeze_incompatible_rate":
        if value <= 0.05:
            return "green"
        if value <= 0.15:
            return "amber"
        return "red"
    return "unknown"


def compute_canonical_stability_metrics(
    db: Any,
    *,
    assignment_id: Optional[int] = None,
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute institutional reproducibility health from submission snapshots.
    """
    from app.models import GradingSummary, Submission, SubmissionStatus

    query = db.query(Submission).filter(Submission.status == SubmissionStatus.COMPLETED)
    if assignment_id is not None:
        query = query.filter(Submission.assignment_id == assignment_id)
    if batch_id is not None:
        query = query.filter(Submission.batch_id == batch_id)

    subs = query.order_by(Submission.id.asc()).all()

    total = len(subs)
    with_governance = 0
    governance_clean = 0
    canonical_count = 0
    superseded_count = 0
    replay_reuse_count = 0
    override_count = 0
    freeze_incompatible = 0
    canonical_drift_incidents: List[Dict[str, Any]] = []
    freeze_drift_signals: List[Dict[str, Any]] = []
    unique_hashes: Dict[str, Dict[str, Any]] = {}

    for sub in subs:
        summary = (
            db.query(GradingSummary).filter(GradingSummary.submission_id == sub.id).first()
        )
        rec = load_submission_governance_record(sub, summary)
        snap = rec.get("snapshot") or {}
        gov = parse_snapshot_governance(snap)

        if gov:
            with_governance += 1
            if (
                gov.get("governance_state") in ("approved", "canonical")
                and gov.get("drift_status") == "clean"
                and gov.get("institutional_status") == "canonical"
            ):
                governance_clean += 1
            if gov.get("institutional_status") == "canonical":
                canonical_count += 1
            if gov.get("institutional_status") == "superseded":
                superseded_count += 1
            if gov.get("reviewer_override"):
                override_count += 1

        if snap.get("cached") or snap.get("cached_from_submission_id"):
            replay_reuse_count += 1

        for inc in snap.get("governance_incidents") or []:
            if inc.get("failure_mode_id") == TAXONOMY_DRIFT_MODE:
                canonical_drift_incidents.append(
                    {
                        "submission_id": sub.id,
                        "batch_id": sub.batch_id,
                        "student_name": sub.student_name,
                        **inc,
                    }
                )

        drift_report = analyze_submission_governance_drift(snap) if snap else {}
        if drift_report.get("status") in ("drift_detected", "critical"):
            freeze_incompatible += 1
        for sig in drift_report.get("drift_signals") or []:
            freeze_drift_signals.append(classify_drift_signal({**sig, "submission_id": sub.id}))

        ghash = str(rec.get("grading_hash") or "")
        if ghash:
            bucket = unique_hashes.setdefault(
                ghash,
                {
                    "grading_hash": ghash[:16],
                    "submission_ids": [],
                    "grade_levels": set(),
                },
            )
            bucket["submission_ids"].append(sub.id)
            if rec.get("grade_level"):
                bucket["grade_levels"].add(str(rec["grade_level"]))

    hash_divergence = sum(
        1 for h in unique_hashes.values() if len(h["grade_levels"]) > 1
    )

    metrics = {
        "canonical_drift_rate": _safe_ratio(len(canonical_drift_incidents), total),
        "supersession_frequency": _safe_ratio(superseded_count, total),
        "replay_reuse_rate": _safe_ratio(replay_reuse_count, total),
        "override_after_canonical_rate": _safe_ratio(override_count, max(canonical_count, 1)),
        "freeze_incompatible_rate": _safe_ratio(freeze_incompatible, total),
        "governance_clean_ratio": _safe_ratio(governance_clean, max(with_governance, 1)),
        "evidence_hash_divergence_rate": _safe_ratio(hash_divergence, max(len(unique_hashes), 1)),
    }

    health = {
        key: {"value": metrics[key], "band": _health_band(key, metrics[key])}
        for key in metrics
    }

    overall_bands = [h["band"] for h in health.values() if h["band"] != "unknown"]
    if any(b == "red" for b in overall_bands):
        overall = "red"
    elif any(b == "amber" for b in overall_bands):
        overall = "amber"
    elif overall_bands:
        overall = "green"
    else:
        overall = "unknown"

    return {
        "report_type": "canonical_stability_metrics",
        "metrics_version": METRICS_VERSION,
        "scope": {
            "assignment_id": assignment_id,
            "batch_id": batch_id,
        },
        "submission_count": total,
        "counts": {
            "with_governance_block": with_governance,
            "governance_clean": governance_clean,
            "canonical": canonical_count,
            "superseded": superseded_count,
            "replay_reuse": replay_reuse_count,
            "reviewer_override": override_count,
            "freeze_incompatible": freeze_incompatible,
            "canonical_drift_incidents": len(canonical_drift_incidents),
            "freeze_drift_signals": len(freeze_drift_signals),
            "unique_evidence_hashes": len(unique_hashes),
            "hash_grade_divergence": hash_divergence,
        },
        "metrics": metrics,
        "health_bands": health,
        "overall_stability": overall,
        "purpose_ar": (
            "قياس صحة reproducibility المؤسسية — drift، supersession، replay، "
            "override — وليس دقة AI."
        ),
        "interpretation_ar": {
            "canonical_drift_rate": "نسبة submissions أنتجت انحرافاً مرجعياً (GFM_CANONICAL_DRIFT)",
            "supersession_frequency": "نسبة snapshots مُعلّمة superseded (variance محفوظة غير authoritative)",
            "replay_reuse_rate": "نسبة استخدام canonical replay بدل re-grade",
            "override_after_canonical_rate": "ضغط التصحيح البشري على canonical",
            "freeze_incompatible_rate": "مخرجات غير متوافقة مع GOVERNANCE_FREEZE_v1",
            "governance_clean_ratio": "snapshots approved + clean + canonical",
            "evidence_hash_divergence_rate": "نفس grading_hash → grade_levels مختلفة",
        },
        "recent_drift_incidents": canonical_drift_incidents[:20],
        "recent_freeze_drift_signals": freeze_drift_signals[:20],
        "epistemic_version_control": {
            "label": "institutional_epistemic_version_control",
            "bounded_historical_variance": superseded_count,
            "canonical_authority_count": canonical_count,
            "note_ar": (
                "superseded snapshots = bounded historical variance — "
                "محفوظة للتدقيق، غير authoritative."
            ),
        },
    }


def attach_to_cohort_synthesis(synthesis: Dict[str, Any], stability: Dict[str, Any]) -> Dict[str, Any]:
    """Merge canonical stability metrics into institutional governance stability report."""
    out = dict(synthesis)
    out["canonical_stability_metrics"] = stability
    out["institutional_stability_observability"] = {
        "layer": "epistemic_version_control",
        "overall_stability": stability.get("overall_stability"),
        "top_risk_metrics": [
            k
            for k, h in (stability.get("health_bands") or {}).items()
            if h.get("band") == "red"
        ],
    }
    return out
