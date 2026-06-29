"""
Shadow-layer reliability metrics — sufficiency, review gates, corroboration (no achieved).

Read-only aggregates for large-scale calibration dashboards.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

SHADOW_METRICS_SCHEMA = "shadow_metrics_v1"


def _norm_crit(level: str) -> str:
    s = (level or "").strip().upper()
    if "." in s:
        s = s.split(".")[-1]
    return s


def extract_row_shadow_signals(
    snapshot: Mapping[str, Any],
    criterion: str,
) -> Dict[str, Any]:
    """Per (submission, criterion) shadow signals from grading snapshot."""
    el = snapshot.get("evidence_layer") or {}
    items = [it for it in (el.get("items") or []) if isinstance(it, dict)]
    rc = el.get("runtime_corroboration") or {}
    cm = el.get("cross_modal_corroboration") or {}
    rub_shadow = el.get("rubric_sufficiency_shadow") or {}
    hr_gates = el.get("human_review_gates") or {}

    crit_norm = _norm_crit(criterion)
    by_crit = rub_shadow.get("by_criterion") or {}
    rub_row = None
    for lvl, row in by_crit.items():
        if _norm_crit(str(lvl)) == crit_norm and isinstance(row, dict):
            rub_row = row
            break

    suff = None
    insuff_flags: List[str] = []
    if isinstance(rub_row, dict):
        if rub_row.get("sufficient") is not None:
            suff = bool(rub_row.get("sufficient"))
        for f in rub_row.get("insufficiency_flags") or []:
            if isinstance(f, dict) and f.get("flag"):
                insuff_flags.append(str(f["flag"]))
    if rub_row is None:
        for cr in snapshot.get("criteria_results") or []:
            if not isinstance(cr, dict):
                continue
            if _norm_crit(str(cr.get("criteria_level") or "")) != crit_norm:
                continue
            snap = cr.get("academic_snapshot") or {}
            rs = snap.get("rubric_shadow_result") or {}
            sr = rs.get("sufficiency_result") or {}
            if sr.get("sufficient") is not None:
                suff = bool(sr.get("sufficient"))
            for f in rs.get("insufficiency_flags") or []:
                if isinstance(f, dict) and f.get("flag"):
                    insuff_flags.append(str(f["flag"]))

    hr_required = None
    hr_severity = None
    hr_reasons: List[str] = []
    hr_by = hr_gates.get("by_criterion") or {}
    for lvl, row in hr_by.items():
        if _norm_crit(str(lvl)) == crit_norm and isinstance(row, dict):
            hrr = row.get("human_review_required") or {}
            hr_required = bool(hrr.get("required")) if hrr.get("required") is not None else None
            hr_severity = hrr.get("severity")
            hr_reasons = list(hrr.get("reasons") or [])
            break
    if hr_required is None:
        for cr in snapshot.get("criteria_results") or []:
            if not isinstance(cr, dict):
                continue
            if _norm_crit(str(cr.get("criteria_level") or "")) != crit_norm:
                continue
            snap = cr.get("academic_snapshot") or {}
            hrr = snap.get("human_review_required") or {}
            if hrr.get("required") is not None:
                hr_required = bool(hrr.get("required"))
            hr_severity = hrr.get("severity")
            hr_reasons = list(hrr.get("reasons") or [])

    pattern_only = bool(items) and all(it.get("evidence_type") == "pattern_hint" for it in items)
    code_collision = any(
        it.get("evidence_type") == "code_system" and it.get("system") == "collision_system"
        for it in items
    )
    conflicts = list(rc.get("corroboration_conflicts") or [])
    cm_flags = [
        str(f.get("flag"))
        for f in (cm.get("cross_modal_noise_flags") or [])
        if isinstance(f, dict) and f.get("flag")
    ]
    try:
        cm_div = float(cm.get("cross_modal_diversity_score") or 0.0)
    except (TypeError, ValueError):
        cm_div = 0.0

    return {
        "criterion": criterion,
        "evidence_item_count": len(items),
        "empty_evidence_layer": len(items) == 0,
        "pattern_hint_only": pattern_only,
        "has_code_collision_system": code_collision,
        "rubric_shadow_sufficient": suff,
        "insufficiency_flags": insuff_flags,
        "human_review_required": hr_required,
        "human_review_severity": hr_severity,
        "human_review_reasons": hr_reasons,
        "corroboration_conflict_count": len(conflicts),
        "cross_modal_diversity_score": cm_div,
        "cross_modal_noise_flags": cm_flags,
        "video_only_windows": "video_frames_present_without_temporal_overlap" in cm_flags
        and any(
            isinstance(f, dict)
            and str(f.get("detail") or "").find("video_only") >= 0
            for f in (cm.get("cross_modal_noise_flags") or [])
        ),
    }


def _severity_histogram(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    c: Counter = Counter()
    for r in rows:
        sev = str(r.get("human_review_severity") or "unknown")
        c[sev] += 1
    return dict(sorted(c.items()))


def build_review_gate_dashboard(evaluated_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(evaluated_rows)
    required_rows = [r for r in evaluated_rows if r.get("human_review_required") is True]
    inflation = len(required_rows) / n if n else 0.0
    reason_counter: Counter = Counter()
    for r in required_rows:
        for reason in r.get("human_review_reasons") or []:
            reason_counter[str(reason)] += 1

    return {
        "schema": "review_gate_dashboard_v1",
        "rows_evaluated": n,
        "human_review_required_count": len(required_rows),
        "human_review_required_rate": round(inflation, 4),
        "severity_distribution": _severity_histogram(evaluated_rows),
        "top_review_reasons": dict(reason_counter.most_common(15)),
        "interpretation_notes": [
            "Rates above ~0.6 on a balanced cohort suggest review gate inflation.",
            "Severity skew toward high/critical without FP correlation also warrants trigger audit.",
        ],
    }


def build_sufficiency_shadow_dashboard(
    evaluated_rows: List[Dict[str, Any]],
    *,
    gold_pairs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    n = len(evaluated_rows)
    with_suff = [r for r in evaluated_rows if r.get("rubric_shadow_sufficient") is not None]
    sufficient_true = sum(1 for r in with_suff if r.get("rubric_shadow_sufficient"))
    insuff_counter: Counter = Counter()
    for r in evaluated_rows:
        for f in r.get("insufficiency_flags") or []:
            insuff_counter[str(f)] += 1

    teacher_agreement = None
    if gold_pairs:
        agree = disagree = 0
        for gp in gold_pairs:
            t_ach = gp.get("teacher_achieved")
            suff = gp.get("rubric_shadow_sufficient")
            if suff is None or t_ach is None:
                continue
            if bool(t_ach) == bool(suff):
                agree += 1
            else:
                disagree += 1
        denom = agree + disagree
        teacher_agreement = {
            "rows_with_both_labels": denom,
            "agreement_rate": round(agree / denom, 4) if denom else None,
            "disagreement_rate": round(disagree / denom, 4) if denom else None,
            "note": "Shadow sufficiency vs teacher achieved — observational only; do not wire to grading.",
        }

    return {
        "schema": "sufficiency_shadow_dashboard_v1",
        "rows_evaluated": n,
        "rows_with_shadow_sufficient_label": len(with_suff),
        "shadow_sufficient_rate": round(sufficient_true / len(with_suff), 4) if with_suff else None,
        "insufficiency_flag_counts": dict(insuff_counter.most_common(20)),
        "teacher_shadow_agreement": teacher_agreement,
    }


def build_corroboration_dashboard(evaluated_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(evaluated_rows)
    pattern_only = sum(1 for r in evaluated_rows if r.get("pattern_hint_only"))
    empty_ev = sum(1 for r in evaluated_rows if r.get("empty_evidence_layer"))
    conflict_rows = sum(
        1 for r in evaluated_rows if int(r.get("corroboration_conflict_count") or 0) > 0
    )
    video_only = sum(1 for r in evaluated_rows if r.get("video_only_windows"))
    divs = [
        float(r.get("cross_modal_diversity_score") or 0.0)
        for r in evaluated_rows
        if r.get("cross_modal_diversity_score") is not None
    ]
    mean_div = round(sum(divs) / len(divs), 4) if divs else None

    return {
        "schema": "corroboration_dashboard_v1",
        "rows_evaluated": n,
        "pattern_hint_only_rate": round(pattern_only / n, 4) if n else None,
        "empty_evidence_layer_rate": round(empty_ev / n, 4) if n else None,
        "rows_with_corroboration_conflicts_rate": round(conflict_rows / n, 4) if n else None,
        "video_only_windows_rate": round(video_only / n, 4) if n else None,
        "mean_cross_modal_diversity_score": mean_div,
    }


def build_shadow_metrics_block(
    evaluated_rows: List[Dict[str, Any]],
    *,
    gold_evaluated: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    gold_pairs = None
    if gold_evaluated:
        gold_pairs = [
            {
                "teacher_achieved": g.get("teacher_achieved"),
                "rubric_shadow_sufficient": g.get("rubric_shadow_sufficient"),
            }
            for g in gold_evaluated
        ]
    return {
        "schema": SHADOW_METRICS_SCHEMA,
        "review_gate_dashboard": build_review_gate_dashboard(evaluated_rows),
        "sufficiency_shadow_dashboard": build_sufficiency_shadow_dashboard(
            evaluated_rows, gold_pairs=gold_pairs
        ),
        "corroboration_dashboard": build_corroboration_dashboard(evaluated_rows),
    }
