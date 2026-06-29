"""
Reliability calibration pipeline (gold teacher labels vs system + shadow dashboards).

1. Populate `gold_dataset/` with real teacher labels (target 100–300 rows).
2. Export `system_snapshots.json` from batch grading exports.
3. Run `run_large_scale_calibration` inside a documented freeze window.

Synthetic cohort: `generate_synthetic_gold_cohort` for pipeline validation only.

Reliability stress: `generate_reliability_stress_cohort` + `run_reliability_stress_cycle` (failure-oriented, not production validation).

Temporal drift: `calibration_diff` compares two saved reports (baseline vs candidate).
"""
