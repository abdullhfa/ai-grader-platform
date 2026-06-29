"""
Large-scale calibration — teacher gold vs system + shadow reliability dashboards.

Usage (repo root):
  python -m app.calibration.generate_synthetic_gold_cohort --count 100
  python -m app.calibration.run_large_scale_calibration \\
    --gold app/calibration/gold_dataset/unity_gold_synthetic_cohort_v1.json \\
    --systems app/calibration/gold_dataset/system_snapshots_synthetic_cohort_v1.json \\
    --out app/calibration/reports/synthetic_cohort_run.json \\
    --freeze-window freeze_synthetic_pipeline_v1

Does NOT change thresholds or wire shadow to achieved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.calibration.calibration_report import build_calibration_report, pick_meta


def main() -> int:
    ap = argparse.ArgumentParser(description="Large-scale calibration report")
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--systems", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--run-id", type=str, default=None)
    ap.add_argument("--rubric-version", type=str, default=None)
    ap.add_argument("--extractor-version", type=str, default=None)
    ap.add_argument("--freeze-window", type=str, default=None, help="Freeze window label")
    ap.add_argument("--stdout", action="store_true", help="Also print JSON to stdout")
    args = ap.parse_args()

    if not args.gold.is_file():
        print(f"gold not found: {args.gold}", file=sys.stderr)
        return 1
    if not args.systems.is_file():
        print(f"systems not found: {args.systems}", file=sys.stderr)
        return 1

    report = build_calibration_report(
        args.gold,
        args.systems,
        run_id=pick_meta(args.run_id, "CALIBRATION_RUN_ID"),
        rubric_version=pick_meta(args.rubric_version, "RUBRIC_VERSION"),
        extractor_version=pick_meta(args.extractor_version, "EXTRACTOR_VERSION"),
        freeze_window_id=(args.freeze_window or "").strip() or None,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    m = report.get("metrics") or {}
    sd = report.get("shadow_dashboard") or {}
    rg = (sd.get("review_gate_dashboard") or {}) if isinstance(sd, dict) else {}
    print(f"Wrote {args.out}")
    print(
        f"pairs={report.get('cohort_summary', {}).get('pairs_compared')} "
        f"FP={m.get('false_positives')} FN={m.get('false_negatives')} "
        f"review_required_rate={rg.get('human_review_required_rate')}"
    )

    if args.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
