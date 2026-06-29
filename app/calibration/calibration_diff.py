"""
Temporal reliability diff — compare two calibration reports (baseline vs candidate).

Observational only: does not declare which run is "better".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

CALIBRATION_DIFF_SCHEMA = "calibration_diff_v1"

# Rate deltas (absolute difference in proportion points expressed as fraction)
_RATE_LOW = 0.05
_RATE_MEDIUM = 0.12
_RATE_HIGH = 0.20

# Integer count deltas
_COUNT_LOW = 3
_COUNT_MEDIUM = 10
_COUNT_HIGH = 20


def load_report(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"report must be object: {path}")
    return data


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _delta_int(baseline: int, candidate: int) -> int:
    return candidate - baseline


def _delta_rate(baseline: Optional[float], candidate: Optional[float]) -> Optional[float]:
    if baseline is None and candidate is None:
        return None
    return round(_f(candidate) - _f(baseline), 4)


def _drift_severity_abs(delta: Optional[float], *, rate: bool = True) -> str:
    if delta is None:
        return "unknown"
    a = abs(delta)
    if rate:
        if a < _RATE_LOW:
            return "low"
        if a < _RATE_MEDIUM:
            return "medium"
        return "high"
    if a < _COUNT_LOW:
        return "low"
    if a < _COUNT_MEDIUM:
        return "medium"
    return "high"


def _drift_severity_count(delta: int) -> str:
    return _drift_severity_abs(float(delta), rate=False)


def _metrics_block(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(report.get("metrics") or {})


def _shadow(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(report.get("shadow_dashboard") or {})


def _review_gate(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(_shadow(report).get("review_gate_dashboard") or {})


def _sufficiency(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(_shadow(report).get("sufficiency_shadow_dashboard") or {})


def _corroboration(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(_shadow(report).get("corroboration_dashboard") or {})


def _fp_density(report: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(report.get("false_positive_density_report") or {})


def _taxonomy_counts(report: Mapping[str, Any]) -> Dict[str, int]:
    raw = report.get("error_taxonomy_suggested_counts") or {}
    return {str(k): _i(v) for k, v in raw.items()}


def _severity_dist(report: Mapping[str, Any]) -> Dict[str, int]:
    raw = _review_gate(report).get("severity_distribution") or {}
    return {str(k): _i(v) for k, v in raw.items()}


def _severity_delta(
    base: Dict[str, int], cand: Dict[str, int]
) -> Dict[str, int]:
    keys = set(base) | set(cand)
    return {k: _i(cand.get(k)) - _i(base.get(k)) for k in sorted(keys)}


def _count_delta_dict(
    base: Dict[str, int], cand: Dict[str, int]
) -> Dict[str, int]:
    keys = set(base) | set(cand)
    return {k: _i(cand.get(k)) - _i(base.get(k)) for k in sorted(keys)}


def _insufficiency_counts(report: Mapping[str, Any]) -> Dict[str, int]:
    raw = _sufficiency(report).get("insufficiency_flag_counts") or {}
    return {str(k): _i(v) for k, v in raw.items()}


def _benchmark_consistency(
    base_run: Mapping[str, Any],
    cand_run: Mapping[str, Any],
) -> Dict[str, Any]:
    flags: List[Dict[str, str]] = []
    notes: List[str] = []

    def _basename(p: Any) -> str:
        return Path(str(p or "")).name

    base_inputs = base_run.get("inputs") or {}
    cand_inputs = cand_run.get("inputs") or {}
    base_gold = _basename(base_inputs.get("gold_path"))
    cand_gold = _basename(cand_inputs.get("gold_path"))

    same_gold = base_gold == cand_gold and bool(base_gold)
    same_systems = _basename(base_inputs.get("systems_path")) == _basename(
        cand_inputs.get("systems_path")
    )
    base_rubric = base_run.get("rubric_version")
    cand_rubric = cand_run.get("rubric_version")
    base_freeze = base_run.get("freeze_window_id")
    cand_freeze = cand_run.get("freeze_window_id")
    base_run_id = base_run.get("run_id")
    cand_run_id = cand_run.get("run_id")

    if not same_gold:
        flags.append({"flag": "benchmark_mismatch", "detail": "gold_dataset_path"})
    if not same_systems:
        flags.append({"flag": "benchmark_mismatch", "detail": "systems_snapshot_path"})
    if base_rubric != cand_rubric and (base_rubric or cand_rubric):
        flags.append({"flag": "benchmark_mismatch", "detail": "rubric_version"})
    if base_freeze != cand_freeze and (base_freeze or cand_freeze):
        flags.append({"flag": "benchmark_mismatch", "detail": "freeze_window_id"})

    if base_run_id == cand_run_id and base_run_id:
        notes.append("same_run_id_warning: baseline and candidate share run_id")

    comparable = len(flags) == 0
    return {
        "comparable": comparable,
        "baseline_run_id": base_run_id,
        "candidate_run_id": cand_run_id,
        "baseline_freeze_window_id": base_freeze,
        "candidate_freeze_window_id": cand_freeze,
        "same_gold_file": same_gold,
        "same_systems_file": same_systems,
        "gold_file_baseline": base_gold,
        "gold_file_candidate": cand_gold,
        "rubric_version_baseline": base_rubric,
        "rubric_version_candidate": cand_rubric,
        "flags": flags,
        "notes": notes,
    }


def _build_confusion_deltas(
    base_m: Mapping[str, Any], cand_m: Mapping[str, Any]
) -> Dict[str, Any]:
    fields = ("true_positives", "false_positives", "false_negatives", "true_negatives")
    deltas: Dict[str, Any] = {}
    for f in fields:
        b = _i(base_m.get(f))
        c = _i(cand_m.get(f))
        d = c - b
        deltas[f"{f}_delta"] = d
        deltas[f"{f}_baseline"] = b
        deltas[f"{f}_candidate"] = c
        deltas[f"{f}_drift_severity"] = _drift_severity_count(d)

    fp_rate_d = _delta_rate(base_m.get("false_positive_rate"), cand_m.get("false_positive_rate"))
    fn_rate_d = _delta_rate(base_m.get("false_negative_rate"), cand_m.get("false_negative_rate"))
    prec_d = _delta_rate(base_m.get("precision_achieved_class"), cand_m.get("precision_achieved_class"))
    f1_d = _delta_rate(base_m.get("f1_achieved_class"), cand_m.get("f1_achieved_class"))

    return {
        **deltas,
        "false_positive_rate_delta": fp_rate_d,
        "false_negative_rate_delta": fn_rate_d,
        "precision_achieved_class_delta": prec_d,
        "f1_achieved_class_delta": f1_d,
        "false_positive_rate_drift_severity": _drift_severity_abs(fp_rate_d),
        "false_negative_rate_drift_severity": _drift_severity_abs(fn_rate_d),
    }


def _build_review_gate_deltas(
    base: Mapping[str, Any], cand: Mapping[str, Any]
) -> Dict[str, Any]:
    b_rate = _f(base.get("human_review_required_rate"))
    c_rate = _f(cand.get("human_review_required_rate"))
    rate_delta = round(c_rate - b_rate, 4)
    b_sev = _severity_dist({"shadow_dashboard": {"review_gate_dashboard": base}})
    c_sev = _severity_dist({"shadow_dashboard": {"review_gate_dashboard": cand}})
    return {
        "human_review_required_rate_baseline": b_rate,
        "human_review_required_rate_candidate": c_rate,
        "human_review_required_rate_delta": rate_delta,
        "human_review_required_rate_drift_severity": _drift_severity_abs(rate_delta),
        "severity_distribution_delta": _severity_delta(b_sev, c_sev),
        "top_review_reasons_delta": _count_delta_dict(
            {str(k): _i(v) for k, v in (base.get("top_review_reasons") or {}).items()},
            {str(k): _i(v) for k, v in (cand.get("top_review_reasons") or {}).items()},
        ),
    }


def _build_shadow_deltas(
    base_report: Mapping[str, Any], cand_report: Mapping[str, Any]
) -> Dict[str, Any]:
    base_suff = _sufficiency(base_report)
    cand_suff = _sufficiency(cand_report)
    base_corr = _corroboration(base_report)
    cand_corr = _corroboration(cand_report)

    suff_rate_b = base_suff.get("shadow_sufficient_rate")
    suff_rate_c = cand_suff.get("shadow_sufficient_rate")
    suff_rate_delta = _delta_rate(suff_rate_b, suff_rate_c)

    agree_b = (base_suff.get("teacher_shadow_agreement") or {}).get("agreement_rate")
    agree_c = (cand_suff.get("teacher_shadow_agreement") or {}).get("agreement_rate")
    agree_delta = _delta_rate(agree_b, agree_c)

    pattern_b = _f(base_corr.get("pattern_hint_only_rate"))
    pattern_c = _f(cand_corr.get("pattern_hint_only_rate"))
    pattern_delta = round(pattern_c - pattern_b, 4)

    conflict_b = _f(base_corr.get("rows_with_corroboration_conflicts_rate"))
    conflict_c = _f(cand_corr.get("rows_with_corroboration_conflicts_rate"))
    conflict_delta = round(conflict_c - conflict_b, 4)

    cm_div_b = _f(base_corr.get("mean_cross_modal_diversity_score"))
    cm_div_c = _f(cand_corr.get("mean_cross_modal_diversity_score"))
    cm_div_delta = round(cm_div_c - cm_div_b, 4)

    return {
        "shadow_sufficient_rate_delta": suff_rate_delta,
        "teacher_shadow_agreement_rate_delta": agree_delta,
        "pattern_hint_only_rate_delta": pattern_delta,
        "corroboration_conflicts_rate_delta": conflict_delta,
        "mean_cross_modal_diversity_score_delta": cm_div_delta,
        "insufficiency_flag_counts_delta": _count_delta_dict(
            _insufficiency_counts(base_report), _insufficiency_counts(cand_report)
        ),
        "pattern_hint_only_rate_drift_severity": _drift_severity_abs(pattern_delta),
        "corroboration_conflicts_rate_drift_severity": _drift_severity_abs(conflict_delta),
    }


def _build_fp_empty_drift(
    base_report: Mapping[str, Any], cand_report: Mapping[str, Any]
) -> Dict[str, Any]:
    base_fp = _fp_density(base_report)
    cand_fp = _fp_density(cand_report)
    b_ratio = base_fp.get("fp_empty_evidence_layer_ratio")
    c_ratio = cand_fp.get("fp_empty_evidence_layer_ratio")
    delta = _delta_rate(b_ratio, c_ratio)
    return {
        "fp_empty_evidence_layer_ratio_baseline": b_ratio,
        "fp_empty_evidence_layer_ratio_candidate": c_ratio,
        "fp_empty_evidence_layer_ratio_delta": delta,
        "fp_empty_evidence_layer_drift_severity": _drift_severity_abs(delta),
        "false_positives_total_delta": _delta_int(
            _i(base_fp.get("false_positives_total")),
            _i(cand_fp.get("false_positives_total")),
        ),
    }


def _derive_flags_and_notes(diffs: Mapping[str, Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[str]]:
    regression: List[Dict[str, str]] = []
    improvement: List[Dict[str, str]] = []
    notes: List[str] = []

    conf = diffs.get("confusion_deltas") or {}
    rg = diffs.get("review_gate_deltas") or {}
    sh = diffs.get("shadow_deltas") or {}
    fp_empty = diffs.get("fp_empty_evidence_drift") or {}

    fp_d = _i(conf.get("false_positives_delta"))
    fn_d = _i(conf.get("false_negatives_delta"))
    fp_rate_d = conf.get("false_positive_rate_delta")
    review_rate_d = rg.get("human_review_required_rate_delta")
    pattern_d = sh.get("pattern_hint_only_rate_delta")
    conflict_d = sh.get("corroboration_conflicts_rate_delta")
    agree_d = sh.get("teacher_shadow_agreement_rate_delta")
    empty_d = fp_empty.get("fp_empty_evidence_layer_ratio_delta")

    if fp_d > _COUNT_MEDIUM or (fp_rate_d is not None and fp_rate_d > _RATE_MEDIUM):
        regression.append({"flag": "false_positive_regression"})
        notes.append("candidate run increased false positives vs baseline")
    elif fp_d < -_COUNT_LOW or (fp_rate_d is not None and fp_rate_d < -_RATE_LOW):
        improvement.append({"flag": "reduced_false_positives"})
        notes.append("candidate run reduced false positives vs baseline")

    if fn_d > _COUNT_LOW:
        regression.append({"flag": "false_negative_regression"})
        notes.append("candidate run increased false negatives vs baseline")
    elif fn_d < -_COUNT_LOW:
        improvement.append({"flag": "reduced_false_negatives"})

    if review_rate_d is not None and review_rate_d > _RATE_MEDIUM:
        regression.append({"flag": "review_gate_inflation"})
        notes.append("candidate run increased human_review_required escalation")
    elif review_rate_d is not None and review_rate_d < -_RATE_LOW:
        improvement.append({"flag": "reduced_review_gate_escalation"})
        notes.append("candidate run lowered human review escalation rate")

    if pattern_d is not None and pattern_d > _RATE_LOW:
        regression.append({"flag": "pattern_hint_dependence_regression"})
    elif pattern_d is not None and pattern_d < -_RATE_LOW:
        improvement.append({"flag": "reduced_pattern_hint_dependence"})

    if conflict_d is not None and conflict_d > _RATE_LOW:
        regression.append({"flag": "cross_modal_conflict_regression"})
    elif conflict_d is not None and conflict_d < -_RATE_LOW:
        improvement.append({"flag": "reduced_cross_modal_conflicts"})

    if agree_d is not None and agree_d > _RATE_LOW:
        improvement.append({"flag": "improved_sufficiency_agreement"})
    elif agree_d is not None and agree_d < -_RATE_LOW:
        regression.append({"flag": "sufficiency_agreement_regression"})

    if empty_d is not None and empty_d > _RATE_LOW:
        regression.append({"flag": "fp_empty_evidence_regression"})
    elif empty_d is not None and empty_d < -_RATE_LOW:
        improvement.append({"flag": "reduced_fp_empty_evidence"})

    if fp_d < -_COUNT_LOW and review_rate_d is not None and review_rate_d > _RATE_MEDIUM:
        notes.append(
            "candidate reduced FP but increased human review escalation — mixed reliability shift"
        )
    if fp_d > _COUNT_LOW and review_rate_d is not None and review_rate_d < -_RATE_LOW:
        notes.append(
            "candidate worsened FP but reduced review escalation — mixed reliability shift"
        )

    sev_delta = rg.get("severity_distribution_delta") or {}
    if _i(sev_delta.get("critical")) > 5:
        regression.append({"flag": "critical_severity_escalation"})
    if _i(sev_delta.get("high")) > 10:
        notes.append("high-severity human review bucket grew materially")

    return regression, improvement, notes


def _calibration_stability_summary(
    regression_flags: List[Dict[str, str]],
    diffs: Mapping[str, Any],
    benchmark: Mapping[str, Any],
) -> Dict[str, Any]:
    reasons: List[str] = []
    if not benchmark.get("comparable"):
        reasons.append("benchmark_mismatch_between_runs")
    for row in regression_flags:
        f = row.get("flag")
        if f:
            reasons.append(str(f))

    conf = diffs.get("confusion_deltas") or {}
    if conf.get("false_positive_rate_drift_severity") == "high":
        reasons.append("high_false_positive_rate_drift")
    rg = diffs.get("review_gate_deltas") or {}
    if rg.get("human_review_required_rate_drift_severity") == "high":
        reasons.append("review_escalation_inflation")

    stable = len(reasons) == 0
    return {
        "stable": stable,
        "reasons": reasons,
        "interpretation": (
            "no_material_reliability_drift_detected"
            if stable
            else "material_drift_requires_review_before_threshold_changes"
        ),
    }


def build_calibration_diff(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare two calibration reports; observational diff only."""
    base_run = baseline.get("reliability_run") or {}
    cand_run = candidate.get("reliability_run") or {}
    benchmark = _benchmark_consistency(base_run, cand_run)

    base_m = _metrics_block(baseline)
    cand_m = _metrics_block(candidate)

    confusion_deltas = _build_confusion_deltas(base_m, cand_m)
    review_gate_deltas = _build_review_gate_deltas(
        _review_gate(baseline), _review_gate(candidate)
    )
    shadow_deltas = _build_shadow_deltas(baseline, candidate)
    fp_empty_drift = _build_fp_empty_drift(baseline, candidate)
    taxonomy_delta = _count_delta_dict(
        _taxonomy_counts(baseline), _taxonomy_counts(candidate)
    )

    diffs = {
        "confusion_deltas": confusion_deltas,
        "review_gate_deltas": review_gate_deltas,
        "shadow_deltas": shadow_deltas,
        "fp_empty_evidence_drift": fp_empty_drift,
        "error_taxonomy_suggested_counts_delta": taxonomy_delta,
    }

    regression_flags, improvement_flags, interpretation_notes = _derive_flags_and_notes(diffs)

    overall_severities = [
        confusion_deltas.get("false_positive_rate_drift_severity"),
        review_gate_deltas.get("human_review_required_rate_drift_severity"),
        shadow_deltas.get("pattern_hint_only_rate_drift_severity"),
        fp_empty_drift.get("fp_empty_evidence_layer_drift_severity"),
    ]
    high_count = sum(1 for s in overall_severities if s == "high")
    medium_count = sum(1 for s in overall_severities if s == "medium")
    if high_count >= 2:
        drift_severity = "high"
    elif high_count >= 1 or medium_count >= 2:
        drift_severity = "medium"
    else:
        drift_severity = "low"

    stability = _calibration_stability_summary(regression_flags, diffs, benchmark)

    return {
        "schema": CALIBRATION_DIFF_SCHEMA,
        "observational_only": True,
        "baseline_run_id": base_run.get("run_id"),
        "candidate_run_id": cand_run.get("run_id"),
        "benchmark_consistency": benchmark,
        "drift_severity": drift_severity,
        "confusion_deltas": confusion_deltas,
        "review_gate_deltas": review_gate_deltas,
        "shadow_deltas": shadow_deltas,
        "fp_empty_evidence_drift": fp_empty_drift,
        "error_taxonomy_suggested_counts_delta": taxonomy_delta,
        "regression_flags": regression_flags,
        "improvement_flags": improvement_flags,
        "interpretation_notes": interpretation_notes,
        "calibration_stability_summary": stability,
        "policy": {
            "auto_declare_winner": False,
            "note": "Diff describes reliability drift only; human review required for promotion decisions.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff two calibration reports (temporal reliability)")
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    baseline = load_report(args.baseline)
    candidate = load_report(args.candidate)
    diff = build_calibration_diff(baseline, candidate)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} drift_severity={diff.get('drift_severity')} stable={diff.get('calibration_stability_summary', {}).get('stable')}")

    if args.stdout:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
