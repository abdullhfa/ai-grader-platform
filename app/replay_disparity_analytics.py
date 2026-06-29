"""
Replay-based Disparity Analytics — comparative descriptive replay analysis.

Read-only overlay — compares profiles under same governance contract,
replay reducer, and replay epoch (epistemic comparability).

Vocabulary: divergence, concentration, dependency, asymmetry, sensitivity.
Never: bias, discrimination, unfair, high risk unfairness.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from statistics import pstdev
from typing import Any, Dict, List, Optional, Set

from app.academic_event_replay import build_academic_timeline_replay
from app.authority_transition_replay import build_authority_transition_replay
from app.counterfactual_replay import detect_governance_drift
from app.deterministic_replay_engine import verify_deterministic_replay
from app.governance_contract_registry import DEFAULT_BASELINE_CONTRACT, DEFAULT_COMPARISON_CONTRACT
from app.procedural_fairness_analytics import extract_procedural_path
from app.replay_cohort_registry import (
    COHORT_DEFINITION_CONTRACT,
    classify_composite_zones,
    classify_replay_cohorts,
    get_cohort_label,
    list_cohort_registry,
)

DISPARITY_CONTRACT_DEFAULT = "replay_disparity_v1"
COMPARISON_BASIS_DEFAULT = "same_epoch_same_contract"
REPLAY_REDUCER_DEFAULT = "1.0"
ANALYTICS_MODE = "replay_disparity_analytical_overlay"


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


def _resolve_governance_contract(snap: Dict[str, Any]) -> str:
    rev = snap.get("explainability_revision") or {}
    policy = rev.get("policy_version") or rev.get("governance_contract")
    if policy:
        return str(policy)
    obs = (snap.get("artifact_inventory") or {}).get("runtime_observation_report") or {}
    if "FREEZE_v1" in str(obs.get("reason") or ""):
        return "2.1"
    return "2.1"


def _hold_from_replay_state(state: Dict[str, Any], snap: Dict[str, Any]) -> bool:
    for key in ("P5", "P6"):
        crit = (state.get("criteria") or {}).get(key) or {}
        if isinstance(crit, dict) and crit.get("status") == "HOLD":
            return True
    lineage = (
        (snap.get("explainability_layer") or {}).get("evidence_lineage")
        or snap.get("evidence_lineage")
        or {}
    )
    for key in ("C.P5", "C.P6"):
        crit = (lineage.get("criteria") or {}).get(key) or {}
        if crit.get("status") == "HOLD":
            return True
    return False


def _human_authority_dependency(state: Dict[str, Any], authority_report: Dict[str, Any]) -> bool:
    transitions = authority_report.get("transitions") or []
    if any(t.get("escalation") for t in transitions):
        return True
    for key in ("P5", "P6"):
        crit = (state.get("criteria") or {}).get(key) or {}
        auth = str((crit or {}).get("achievement_authority") or "")
        if "HUMAN" in auth or "L5" in auth:
            return True
    gov = state.get("governance") or {}
    if "HUMAN" in str(gov.get("active_authority") or ""):
        return True
    return False


def _system_finalization(state: Dict[str, Any], hold_present: bool, human_dep: bool) -> bool:
    if hold_present or human_dep:
        return False
    gov = state.get("governance") or {}
    return not bool(gov.get("runtime_gated")) or str(gov.get("active_authority") or "").startswith(
        ("AI_", "SYSTEM")
    )


def _lineage_completeness(snap: Dict[str, Any]) -> float:
    lineage = (
        (snap.get("explainability_layer") or {}).get("evidence_lineage")
        or snap.get("evidence_lineage")
        or {}
    )
    shared = lineage.get("shared_nodes") or {}
    criteria = lineage.get("criteria") or {}
    if not shared and not criteria:
        return 0.0
    node_count = len(shared)
    crit_with_nodes = sum(
        1
        for c in criteria.values()
        if isinstance(c, dict) and (c.get("lineage") or {}).get("evidence_nodes")
    )
    expected = max(len(criteria), 2)
    return round(min(1.0, (node_count / 10.0 + crit_with_nodes / expected) / 2.0), 4)


def _max_drift_severity(drift_report: Dict[str, Any]) -> Optional[str]:
    items = (drift_report.get("drift") or {}).get("drift_items") or []
    order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    best = None
    best_rank = -1
    for item in items:
        sev = str(item.get("severity") or "low")
        rank = order.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


def analyze_submission_replay_disparity(
    submission,
    *,
    graded_at: Optional[str] = None,
    drift_baseline: str = DEFAULT_BASELINE_CONTRACT,
    drift_comparison: str = DEFAULT_COMPARISON_CONTRACT,
) -> Dict[str, Any]:
    """Single submission — replay-derived disparity signals."""
    snap = _load_snapshot(submission)
    sid = getattr(submission, "id", None)
    name = getattr(submission, "student_name", "") or ""

    if not snap or snap.get("success") is False:
        return {"submission_id": sid, "student_name": name, "skipped": True, "reason": "no_snapshot"}

    timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
    events = timeline.get("events") or []
    verification = verify_deterministic_replay(events, snap)
    state = verification.get("state_summary") or {}
    authority = build_authority_transition_replay(snap, events=events)

    path = extract_procedural_path(
        events,
        timeline_source=str(timeline.get("source") or "unknown"),
        snap=snap,
        replay_state=state,
        authority_report=authority,
        verification=verification,
    )

    profiles = classify_replay_cohorts(
        snap,
        replay_state=state,
        procedural_path=path,
    )
    composite_zones = classify_composite_zones(profiles)
    cohorts = list(profiles) + composite_zones

    hold_present = _hold_from_replay_state(state, snap)
    human_dep = _human_authority_dependency(state, authority)
    system_fin = _system_finalization(state, hold_present, human_dep)

    ctx = {
        "evidence_lineage": (
            (snap.get("explainability_layer") or {}).get("evidence_lineage")
            or snap.get("evidence_lineage")
        ),
    }
    drift_report = detect_governance_drift(
        events,
        baseline_contract=drift_baseline,
        comparison_contract=drift_comparison,
        sandbox_context=ctx,
    )
    drift = drift_report.get("drift") or {}

    replay_epoch = str(verification.get("replay_epoch") or "unknown")
    governance_contract = _resolve_governance_contract(snap)
    comparability_key = f"{replay_epoch}|{governance_contract}|{REPLAY_REDUCER_DEFAULT}"

    return {
        "submission_id": sid,
        "student_name": name,
        "skipped": False,
        "evidence_profiles": profiles,
        "composite_zones": composite_zones,
        "replay_cohorts": sorted(set(cohorts)),
        "comparability_key": comparability_key,
        "replay_epoch": replay_epoch,
        "governance_contract": governance_contract,
        "replay_outcome": {
            "hold_present": hold_present,
            "grade_level": state.get("grade_level"),
            "replay_verified": verification.get("replay_verified"),
        },
        "authority_dependency": {
            "human_authority_dependency": human_dep,
            "system_finalization": system_fin,
            "governance_gate_persistent": path.get("governance_gate_persistent"),
            "escalation_count": path.get("escalation_count"),
        },
        "replay_stability": {
            "verification_mismatch": path.get("replay_verification_mismatch"),
            "synthetic_reconstruction": path.get("replay_source_synthetic"),
            "replay_unstable": path.get("replay_unstable"),
            "transition_instability": path.get("repeated_transitions"),
            "lineage_completeness": _lineage_completeness(snap),
        },
        "drift_sensitivity": {
            "counterfactual": True,
            "drift_detected": bool(drift.get("drift_detected")),
            "drift_count": int(drift.get("drift_count") or 0),
            "max_severity": _max_drift_severity(drift_report),
            "baseline_contract": drift_baseline,
            "comparison_contract": drift_comparison,
        },
        "procedural_path": {
            "timeline_source": path.get("timeline_source"),
            "human_escalated": path.get("human_escalated"),
        },
    }


def _cohort_stats_default() -> Dict[str, Any]:
    return {
        "count": 0,
        "hold_count": 0,
        "escalation_count": 0,
        "replay_unstable_count": 0,
        "verification_mismatch_count": 0,
        "human_dependency_count": 0,
        "system_finalization_count": 0,
        "gate_persistent_count": 0,
        "drift_sensitive_count": 0,
        "lineage_completeness_sum": 0.0,
        "transition_instability_count": 0,
    }


def _rate(num: int, den: int) -> float:
    return round(num / max(den, 1), 4)


def _aggregate_cohort(stats: Dict[str, Any]) -> Dict[str, Any]:
    n = int(stats.get("count") or 0)
    lineage_avg = round(float(stats.get("lineage_completeness_sum") or 0) / max(n, 1), 4)
    return {
        "submissions_matched": n,
        "hold_rate": _rate(int(stats.get("hold_count") or 0), n),
        "escalation_rate": _rate(int(stats.get("escalation_count") or 0), n),
        "replay_instability_rate": _rate(int(stats.get("replay_unstable_count") or 0), n),
        "verification_mismatch_rate": _rate(int(stats.get("verification_mismatch_count") or 0), n),
        "human_authority_dependency_rate": _rate(int(stats.get("human_dependency_count") or 0), n),
        "system_finalization_rate": _rate(int(stats.get("system_finalization_count") or 0), n),
        "governance_gate_persistence_rate": _rate(int(stats.get("gate_persistent_count") or 0), n),
        "drift_sensitivity_rate": _rate(int(stats.get("drift_sensitive_count") or 0), n),
        "transition_instability_rate": _rate(int(stats.get("transition_instability_count") or 0), n),
        "avg_lineage_completeness": lineage_avg,
    }


def _accumulate_cohort(stats: Dict[str, Any], row: Dict[str, Any]) -> None:
    stats["count"] += 1
    outcome = row.get("replay_outcome") or {}
    auth = row.get("authority_dependency") or {}
    stability = row.get("replay_stability") or {}
    drift = row.get("drift_sensitivity") or {}
    proc = row.get("procedural_path") or {}

    if outcome.get("hold_present"):
        stats["hold_count"] += 1
    if proc.get("human_escalated") or (auth.get("escalation_count") or 0) > 0:
        stats["escalation_count"] += 1
    if stability.get("replay_unstable"):
        stats["replay_unstable_count"] += 1
    if stability.get("verification_mismatch"):
        stats["verification_mismatch_count"] += 1
    if auth.get("human_authority_dependency"):
        stats["human_dependency_count"] += 1
    if auth.get("system_finalization"):
        stats["system_finalization_count"] += 1
    if auth.get("governance_gate_persistent"):
        stats["gate_persistent_count"] += 1
    if drift.get("drift_detected"):
        stats["drift_sensitive_count"] += 1
    if stability.get("transition_instability"):
        stats["transition_instability_count"] += 1
    stats["lineage_completeness_sum"] += float(stability.get("lineage_completeness") or 0)


def _build_outcome_divergence(
    cohort_rows: List[Dict[str, Any]],
    *,
    batch_baseline: Dict[str, float],
) -> List[Dict[str, Any]]:
    divergence: List[Dict[str, Any]] = []
    for row in cohort_rows:
        cohort = row["cohort"]
        metrics = row["metrics"]
        divergence.append(
            {
                "cohort": cohort,
                "label_ar": get_cohort_label(cohort),
                "hold_rate": metrics["hold_rate"],
                "hold_rate_delta": round(metrics["hold_rate"] - batch_baseline.get("hold_rate", 0), 4),
                "escalation_rate": metrics["escalation_rate"],
                "escalation_rate_delta": round(
                    metrics["escalation_rate"] - batch_baseline.get("escalation_rate", 0), 4
                ),
                "replay_instability_rate": metrics["replay_instability_rate"],
                "replay_instability_delta": round(
                    metrics["replay_instability_rate"]
                    - batch_baseline.get("replay_instability_rate", 0),
                    4,
                ),
                "submissions_matched": metrics["submissions_matched"],
            }
        )
    divergence.sort(key=lambda d: abs(d.get("hold_rate_delta") or 0), reverse=True)
    return divergence


def _build_authority_dependency_disparity(cohort_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in cohort_rows:
        m = item["metrics"]
        rows.append(
            {
                "cohort": item["cohort"],
                "label_ar": get_cohort_label(item["cohort"]),
                "human_authority_dependency_rate": m["human_authority_dependency_rate"],
                "system_finalization_rate": m["system_finalization_rate"],
                "governance_gate_persistence_rate": m["governance_gate_persistence_rate"],
                "dependency_asymmetry_index": round(
                    m["human_authority_dependency_rate"] - m["system_finalization_rate"], 4
                ),
                "submissions_matched": m["submissions_matched"],
            }
        )
    rows.sort(key=lambda r: r["dependency_asymmetry_index"], reverse=True)
    return rows


def _build_replay_stability_disparity(cohort_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    completeness_values = [
        float(item["metrics"]["avg_lineage_completeness"])
        for item in cohort_rows
        if item["metrics"]["submissions_matched"] > 0
    ]
    completeness_variance = round(pstdev(completeness_values), 4) if len(completeness_values) > 1 else 0.0

    rows: List[Dict[str, Any]] = []
    for item in cohort_rows:
        m = item["metrics"]
        rows.append(
            {
                "cohort": item["cohort"],
                "label_ar": get_cohort_label(item["cohort"]),
                "verification_mismatch_rate": m["verification_mismatch_rate"],
                "replay_instability_rate": m["replay_instability_rate"],
                "transition_instability_rate": m["transition_instability_rate"],
                "avg_lineage_completeness": m["avg_lineage_completeness"],
                "lineage_completeness_variance_across_cohorts": completeness_variance,
                "submissions_matched": m["submissions_matched"],
            }
        )
    rows.sort(key=lambda r: r["replay_instability_rate"], reverse=True)
    return rows


def _build_drift_sensitivity_disparity(cohort_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in cohort_rows:
        m = item["metrics"]
        sensitivity = m["drift_sensitivity_rate"]
        rows.append(
            {
                "cohort": item["cohort"],
                "label_ar": get_cohort_label(item["cohort"]),
                "drift_sensitivity_rate": sensitivity,
                "sensitivity_class": (
                    "elevated" if sensitivity >= 0.5 else "moderate" if sensitivity >= 0.25 else "low"
                ),
                "submissions_matched": m["submissions_matched"],
                "counterfactual": True,
            }
        )
    rows.sort(key=lambda r: r["drift_sensitivity_rate"], reverse=True)
    return rows


def _detect_concentration_zones(cohort_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    zones: List[Dict[str, Any]] = []
    for item in cohort_rows:
        m = item["metrics"]
        cohort = item["cohort"]
        signals: List[str] = []
        if m["hold_rate"] >= 0.5:
            signals.append("high_hold_concentration")
        if m["human_authority_dependency_rate"] >= 0.5:
            signals.append("elevated_human_dependency")
        if m["replay_instability_rate"] >= 0.35:
            signals.append("replay_instability")
        if m["verification_mismatch_rate"] >= 0.25:
            signals.append("verification_mismatch_concentration")
        if m["drift_sensitivity_rate"] >= 0.5:
            signals.append("governance_drift_sensitivity")
        if m["governance_gate_persistence_rate"] >= 0.4:
            signals.append("governance_gate_persistence")

        if len(signals) >= 2:
            zones.append(
                {
                    "zone": cohort,
                    "label_ar": get_cohort_label(cohort),
                    "signals": signals,
                    "signal_count": len(signals),
                    "concentration_class": "elevated" if len(signals) >= 3 else "moderate",
                }
            )
    zones.sort(key=lambda z: z["signal_count"], reverse=True)
    return zones


def _build_per_group_divergence(
    comparability_groups: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Outcome divergence scoped to each comparability group — no cross-epoch mixing."""
    groups_out: List[Dict[str, Any]] = []
    for key, group_rows in comparability_groups.items():
        if len(group_rows) < 1:
            continue
        parts = key.split("|")
        epoch = parts[0] if parts else "unknown"
        contract = parts[1] if len(parts) > 1 else "unknown"
        reducer = parts[2] if len(parts) > 2 else REPLAY_REDUCER_DEFAULT

        local_stats: Dict[str, Dict[str, Any]] = defaultdict(_cohort_stats_default)
        for row in group_rows:
            seen: Set[str] = set()
            for cohort in row.get("replay_cohorts") or []:
                if cohort in seen:
                    continue
                seen.add(cohort)
                _accumulate_cohort(local_stats[cohort], row)

        n = len(group_rows) or 1
        baseline = {
            "hold_rate": _rate(
                sum(1 for r in group_rows if (r.get("replay_outcome") or {}).get("hold_present")), n
            ),
            "escalation_rate": _rate(
                sum(1 for r in group_rows if (r.get("procedural_path") or {}).get("human_escalated")),
                n,
            ),
            "replay_instability_rate": _rate(
                sum(1 for r in group_rows if (r.get("replay_stability") or {}).get("replay_unstable")),
                n,
            ),
        }
        cohort_rows = [
            {"cohort": c, "metrics": _aggregate_cohort(st)}
            for c, st in sorted(local_stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
        ]
        groups_out.append(
            {
                "comparability_key": key,
                "replay_epoch": epoch,
                "governance_contract": contract,
                "reducer_version": reducer,
                "submissions": n,
                "batch_baseline": baseline,
                "outcome_divergence": _build_outcome_divergence(cohort_rows, batch_baseline=baseline),
            }
        )
    return groups_out


def _epistemic_comparability_guard(
    comparability_groups: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Warn when batch spans multiple epochs/contracts — cross-group comparison disabled."""
    keys = list(comparability_groups.keys())
    multi = len(keys) > 1
    return {
        "cross_epoch_mixing_detected": multi,
        "comparability_group_count": len(keys),
        "comparison_basis": COMPARISON_BASIS_DEFAULT,
        "cross_contract_disparity_allowed": False,
        "guard_note_ar": (
            "تم رصد أكثر من comparability group — divergence المعروض batch-wide "
            "يُفضّل قراءته ضمن per-group divergence"
            if multi
            else "دفعة ضمن comparability group واحد — batch-wide divergence مستقر epistemically"
        ),
    }


def build_batch_replay_disparity_report(
    db,
    batch_id: int,
    *,
    disparity_contract: str = DISPARITY_CONTRACT_DEFAULT,
    comparison_basis: str = COMPARISON_BASIS_DEFAULT,
    drift_baseline: str = DEFAULT_BASELINE_CONTRACT,
    drift_comparison: str = DEFAULT_COMPARISON_CONTRACT,
) -> Dict[str, Any]:
    """Batch replay disparity — comparative descriptive replay analysis."""
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )

    rows: List[Dict[str, Any]] = []
    cohort_stats: Dict[str, Dict[str, Any]] = defaultdict(_cohort_stats_default)
    comparability_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for sub in subs:
        graded_at = None
        summary = getattr(sub, "summary", None)
        if summary and getattr(summary, "graded_at", None):
            graded_at = summary.graded_at.isoformat() + "Z"
        row = analyze_submission_replay_disparity(
            sub,
            graded_at=graded_at,
            drift_baseline=drift_baseline,
            drift_comparison=drift_comparison,
        )
        rows.append(row)
        if row.get("skipped"):
            continue

        comparability_groups[row["comparability_key"]].append(row)

        seen: Set[str] = set()
        for cohort in row.get("replay_cohorts") or []:
            if cohort in seen:
                continue
            seen.add(cohort)
            _accumulate_cohort(cohort_stats[cohort], row)

    analyzed = [r for r in rows if not r.get("skipped")]
    batch_total = len(analyzed) or 1

    batch_baseline = {
        "hold_rate": _rate(
            sum(1 for r in analyzed if (r.get("replay_outcome") or {}).get("hold_present")), batch_total
        ),
        "escalation_rate": _rate(
            sum(1 for r in analyzed if (r.get("procedural_path") or {}).get("human_escalated")),
            batch_total,
        ),
        "replay_instability_rate": _rate(
            sum(1 for r in analyzed if (r.get("replay_stability") or {}).get("replay_unstable")),
            batch_total,
        ),
    }

    cohort_rows = [
        {"cohort": cohort, "metrics": _aggregate_cohort(stats)}
        for cohort, stats in sorted(cohort_stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    ]

    comparability_summary = [
        {
            "comparability_key": key,
            "replay_epoch": key.split("|")[0] if "|" in key else key,
            "governance_contract": key.split("|")[1] if key.count("|") >= 1 else "unknown",
            "replay_reducer": REPLAY_REDUCER_DEFAULT,
            "submissions": len(group),
            "note_ar": "مقارنة profiles ضمن نفس epoch + contract + reducer",
        }
        for key, group in sorted(comparability_groups.items(), key=lambda kv: -len(kv[1]))
    ]

    epistemic_guard = _epistemic_comparability_guard(comparability_groups)
    per_group_divergence = _build_per_group_divergence(comparability_groups)

    disparity_contract_block = {
        "disparity_contract": disparity_contract,
        "comparison_basis": comparison_basis,
        "governance_contract": "2.1",
        "reducer_version": REPLAY_REDUCER_DEFAULT,
        "cohort_definition_contract": COHORT_DEFINITION_CONTRACT,
    }

    report_id = f"rda_{uuid.uuid4().hex[:16]}"
    body = {
        "report_id": report_id,
        "schema": "1.0",
        "mode": ANALYTICS_MODE,
        "batch_id": batch_id,
        **disparity_contract_block,
        "disparity_contract_spec": disparity_contract_block,
        "replay_cohort_registry": list_cohort_registry(),
        "epistemic_comparability_guard": epistemic_guard,
        "per_group_outcome_divergence": per_group_divergence,
        "drift_analysis": {
            "counterfactual": True,
            "baseline_contract": drift_baseline,
            "comparison_contract": drift_comparison,
            "note_ar": "Drift sensitivity — counterfactual فقط — descriptive",
        },
        "submissions_total": len(subs),
        "submissions_analyzed": len(analyzed),
        "source": "deterministic_replay_engine",
        "read_only": True,
        "normative_boundary_ar": (
            "comparative descriptive replay analysis — divergence / concentration / "
            "dependency / asymmetry — ليس fairness verdict"
        ),
        "disclaimer_ar": (
            "Replay-based Disparity — profiles compared under same epoch + contract. "
            "لا bias / discrimination / unfair verdict."
        ),
        "batch_baseline": batch_baseline,
        "outcome_divergence": _build_outcome_divergence(cohort_rows, batch_baseline=batch_baseline),
        "authority_dependency_disparity": _build_authority_dependency_disparity(cohort_rows),
        "replay_stability_disparity": _build_replay_stability_disparity(cohort_rows),
        "drift_sensitivity_disparity": _build_drift_sensitivity_disparity(cohort_rows),
        "replay_cohort_analysis": cohort_rows,
        "disparity_concentration_zones": _detect_concentration_zones(cohort_rows),
        "comparability_summary": comparability_summary,
        "epistemic_comparability_note_ar": (
            "المقارنة replay-relative — same governance contract · same replay reducer · same epoch"
        ),
        "rows": rows,
        "report_hash": "",
    }
    hash_body = {k: v for k, v in body.items() if k not in ("report_hash", "rows")}
    body["report_hash"] = hashlib.sha256(_stable_json(hash_body).encode("utf-8")).hexdigest()
    return body
