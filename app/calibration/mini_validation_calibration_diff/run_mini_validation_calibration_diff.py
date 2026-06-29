"""
Mini validation for calibration_diff (2 observational scenarios).

Usage:
  python -m app.calibration.mini_validation_calibration_diff.run_mini_validation_calibration_diff
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List


def _i(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _load_base_report() -> Dict[str, Any]:
    p = Path(__file__).resolve().parents[1] / "reports" / "synthetic_cohort_100_v1.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    from app.calibration.calibration_report import build_calibration_report

    gold = Path(__file__).resolve().parents[1] / "gold_dataset" / "unity_gold_synthetic_cohort_v1.json"
    systems = (
        Path(__file__).resolve().parents[1]
        / "gold_dataset"
        / "system_snapshots_synthetic_cohort_v1.json"
    )
    return build_calibration_report(
        gold,
        systems,
        run_id="cal_synthetic_100_baseline",
        freeze_window_id="freeze_diff_mini_v1",
    )


def _fixture_case_a(base: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Candidate: fewer FP, higher review escalation."""
    baseline = copy.deepcopy(base)
    baseline["reliability_run"] = {
        **(baseline.get("reliability_run") or {}),
        "run_id": "baseline_case_a",
        "freeze_window_id": "freeze_diff_mini_v1",
    }
    candidate = copy.deepcopy(base)
    candidate["reliability_run"] = {
        **(candidate.get("reliability_run") or {}),
        "run_id": "candidate_case_a",
        "freeze_window_id": "freeze_diff_mini_v1",
    }
    candidate["metrics"]["false_positives"] = max(0, _i(candidate["metrics"]["false_positives"]) - 25)
    candidate["metrics"]["true_positives"] = _i(candidate["metrics"]["true_positives"]) + 15
    candidate["metrics"]["true_negatives"] = _i(candidate["metrics"]["true_negatives"]) + 10
    pairs = _i(candidate.get("cohort_summary", {}).get("pairs_compared")) or 100
    candidate["metrics"]["false_positive_rate"] = round(
        candidate["metrics"]["false_positives"] / pairs, 4
    )
    rg = candidate["shadow_dashboard"]["review_gate_dashboard"]
    rg["human_review_required_rate"] = min(1.0, _f(rg["human_review_required_rate"]) + 0.18)
    rg["human_review_required_count"] = int(pairs * rg["human_review_required_rate"])
    sev = dict(rg.get("severity_distribution") or {})
    sev["medium"] = _i(sev.get("medium")) + 10
    sev["high"] = _i(sev.get("high")) + 8
    rg["severity_distribution"] = sev
    return baseline, candidate


def _fixture_case_b(base: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Candidate: more FP, lower review escalation."""
    baseline = copy.deepcopy(base)
    baseline["reliability_run"] = {
        **(baseline.get("reliability_run") or {}),
        "run_id": "baseline_case_b",
        "freeze_window_id": "freeze_diff_mini_v1",
    }
    candidate = copy.deepcopy(base)
    candidate["reliability_run"] = {
        **(candidate.get("reliability_run") or {}),
        "run_id": "candidate_case_b",
        "freeze_window_id": "freeze_diff_mini_v1",
    }
    candidate["metrics"]["false_positives"] = _i(candidate["metrics"]["false_positives"]) + 20
    candidate["metrics"]["true_negatives"] = max(0, _i(candidate["metrics"]["true_negatives"]) - 20)
    pairs = _i(candidate.get("cohort_summary", {}).get("pairs_compared")) or 100
    candidate["metrics"]["false_positive_rate"] = round(
        candidate["metrics"]["false_positives"] / pairs, 4
    )
    rg = candidate["shadow_dashboard"]["review_gate_dashboard"]
    rg["human_review_required_rate"] = max(0.0, _f(rg["human_review_required_rate"]) - 0.15)
    rg["human_review_required_count"] = int(pairs * rg["human_review_required_rate"])
    corr = candidate["shadow_dashboard"]["corroboration_dashboard"]
    corr["pattern_hint_only_rate"] = max(0.0, _f(corr.get("pattern_hint_only_rate")) - 0.1)
    return baseline, candidate


def _compact(diff: Dict[str, Any]) -> Dict[str, Any]:
    conf = diff.get("confusion_deltas") or {}
    rg = diff.get("review_gate_deltas") or {}
    return {
        "drift_severity": diff.get("drift_severity"),
        "stable": (diff.get("calibration_stability_summary") or {}).get("stable"),
        "false_positives_delta": conf.get("false_positives_delta"),
        "false_positive_rate_delta": conf.get("false_positive_rate_delta"),
        "human_review_required_rate_delta": rg.get("human_review_required_rate_delta"),
        "regression_flags": [r.get("flag") for r in diff.get("regression_flags") or []],
        "improvement_flags": [r.get("flag") for r in diff.get("improvement_flags") or []],
        "interpretation_notes": diff.get("interpretation_notes"),
        "benchmark_comparable": (diff.get("benchmark_consistency") or {}).get("comparable"),
    }


def run_all() -> Dict[str, Any]:
    from app.calibration.calibration_diff import build_calibration_diff

    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))
    base = _load_base_report()

    fixtures = {
        "case_a_better_fp_higher_review_inflation": _fixture_case_a,
        "case_b_worse_fp_lower_review_escalation": _fixture_case_b,
    }

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        fn = fixtures.get(cid)
        if not fn:
            cases_out.append({**entry, "actual_behavior": json.dumps({"error": "no_fixture"})})
            continue
        baseline, candidate = fn(base)
        diff = build_calibration_diff(baseline, candidate)
        cases_out.append(
            {**entry, "actual_behavior": json.dumps(_compact(diff), ensure_ascii=False, indent=2)}
        )

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_calibration_diff_last_run.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
