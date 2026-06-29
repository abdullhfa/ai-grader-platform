"""
Governance Weighting Layer — counterfactual policy confidence weighting (analytical only).

Compares governance contracts with weighted evidence confidence — never mutates grades.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from app.counterfactual_replay import build_baseline_and_counterfactual, detect_governance_drift
from app.evidence_lineage import CONFIDENCE_WEIGHTS
from app.governance_contract_registry import (
    DEFAULT_BASELINE_CONTRACT,
    DEFAULT_COMPARISON_CONTRACT,
    get_contract,
)

WEIGHTING_CONTRACT = "governance_weighting_v1"
ANALYTICS_MODE = "governance_weighting_counterfactual_overlay"

# Policy-specific multipliers (counterfactual sandbox only)
POLICY_WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "2.1": {
        "human_playtest": 1.0,
        "runtime_observation": 0.85,
        "source_code": 0.75,
        "exe_detected_only": 0.45,
        "documentation": 0.9,
    },
    "2.2": {
        "human_playtest": 1.0,
        "runtime_observation": 1.0,
        "source_code": 0.8,
        "exe_detected_only": 0.55,
        "documentation": 0.85,
    },
}


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_snapshot(submission) -> Optional[Dict[str, Any]]:
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _evidence_tier(snap: Dict[str, Any]) -> str:
    inv = snap.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    if obs.get("human_playtest_verified") or snap.get("l5_human_playtest", {}).get("verified"):
        return "human_playtest"
    if obs.get("status") == "completed":
        return "runtime_observation"
    if inv.get("has_source_code_artifacts") or (inv.get("source_code") or {}).get("files"):
        return "source_code"
    if (inv.get("executable_artifacts") or {}).get("files"):
        return "exe_detected_only"
    return "documentation"


def _weighted_confidence(tier: str, contract_id: str) -> float:
    base = (CONFIDENCE_WEIGHTS.get(tier, 0.5))
    profile = POLICY_WEIGHT_PROFILES.get(contract_id, POLICY_WEIGHT_PROFILES["2.1"])
    mult = (profile.get(tier, 0.5))
    return round(min(1.0, base * mult), 4)


def build_submission_governance_weighting(
    snap: Dict[str, Any],
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
) -> Dict[str, Any]:
    """Per-submission weighted confidence under two governance contracts."""
    tier = _evidence_tier(snap)
    baseline_w = _weighted_confidence(tier, baseline_contract)
    comparison_w = _weighted_confidence(tier, comparison_contract)
    drift = None
    try:
        events = (snap.get("academic_event_log") or {}).get("events") or []
        if events:
            drift = detect_governance_drift(
                events,
                baseline_contract=baseline_contract,
                comparison_contract=comparison_contract,
                sandbox_context={"evidence_lineage": snap.get("evidence_lineage") or {}},
            )
        else:
            pair = build_baseline_and_counterfactual(
                [],
                baseline_contract=baseline_contract,
                comparison_contract=comparison_contract,
            )
            drift = {"baseline_state": pair.get("baseline_state"), "comparison_state": pair.get("comparison_state")}
    except Exception:
        drift = {"error": "drift_replay_unavailable"}

    return {
        "evidence_tier": tier,
        "baseline_contract": baseline_contract,
        "comparison_contract": comparison_contract,
        "baseline_weighted_confidence": baseline_w,
        "comparison_weighted_confidence": comparison_w,
        "confidence_delta": round(comparison_w - baseline_w, 4),
        "contracts": {
            baseline_contract: get_contract(baseline_contract),
            comparison_contract: get_contract(comparison_contract),
        },
        "counterfactual_drift": drift,
        "note_ar": "وزن حوكمة counterfactual — لا يغيّر achieved ولا DB.",
    }


def build_batch_governance_weighting_report(
    db,
    batch_id: int,
    *,
    baseline_contract: str = DEFAULT_BASELINE_CONTRACT,
    comparison_contract: str = DEFAULT_COMPARISON_CONTRACT,
    weighting_contract: str = WEIGHTING_CONTRACT,
) -> Dict[str, Any]:
    from app.models import Submission

    submissions = db.query(Submission).filter(Submission.batch_id == batch_id).all()
    per_sub: List[Dict[str, Any]] = []
    deltas: List[float] = []

    for sub in submissions:
        snap = _load_snapshot(sub)
        if not snap:
            continue
        row = build_submission_governance_weighting(
            snap,
            baseline_contract=baseline_contract,
            comparison_contract=comparison_contract,
        )
        row["submission_id"] = sub.id
        row["student_name"] = sub.student_name
        deltas.append(float(row.get("confidence_delta") or 0))
        per_sub.append(row)

    mean_delta = round(sum(deltas) / max(len(deltas), 1), 4) if deltas else 0.0
    core = {
        "batch_id": batch_id,
        "submission_count": len(per_sub),
        "baseline_contract": baseline_contract,
        "comparison_contract": comparison_contract,
        "mean_confidence_delta": mean_delta,
        "submissions": per_sub,
    }
    digest = hashlib.sha256(_stable_json(core).encode()).hexdigest()[:16]

    return {
        "report_id": f"govweight_{batch_id}_{uuid.uuid4().hex[:8]}",
        "report_type": "governance_weighting_batch",
        "analytics_mode": ANALYTICS_MODE,
        "weighting_contract": weighting_contract,
        "digest": digest,
        **core,
        "interpretation_ar": (
            "مقارنة counterfactual لوزن الثقة تحت عقود حوكمة مختلفة — "
            "لا تُستخدم كسلطة تصحيح."
        ),
    }
