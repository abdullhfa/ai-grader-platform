#!/usr/bin/env python3
"""PHASE A — Run calibration: export snapshots + disagreement report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.calibration.disagreement_report import build_disagreement_report
from app.calibration.human_labels_io import export_system_snapshots_from_db


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE A — Calibration pipeline")
    parser.add_argument(
        "--human-labels",
        default=str(ROOT / "app/calibration/human_labels_v1.json"),
    )
    parser.add_argument(
        "--systems-out",
        default=str(ROOT / "app/calibration/reports/system_snapshots_latest.json"),
    )
    parser.add_argument(
        "--report-out",
        default=str(ROOT / "app/calibration/reports/disagreement_latest.json"),
    )
    parser.add_argument("--submission-id", type=int, action="append", dest="submission_ids")
    parser.add_argument(
        "--cohort-report",
        default="",
        help="Optional runtime cohort report JSON",
    )
    parser.add_argument("--run-id", default="calibration_v1")
    args = parser.parse_args()

    systems_path = Path(args.systems_out)
    export_system_snapshots_from_db(args.submission_ids, systems_path)
    print(f"Exported systems: {systems_path}")

    cohort_path = Path(args.cohort_report) if args.cohort_report else None
    report = build_disagreement_report(
        human_labels_path=Path(args.human_labels),
        systems_path=systems_path,
        cohort_report_path=cohort_path,
        run_id=args.run_id,
    )

    out_path = Path(args.report_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report.get("summary") or {}
    print(f"Disagreement report: {out_path}")
    print(f"Agreement rate: {summary.get('agreement_rate')}")
    print(f"Criterion mismatches: {summary.get('criterion_mismatch_count')}")
    print(f"Replay mismatches: {summary.get('replay_mismatch_count')}")
    print(f"Gold rows used: {summary.get('gold_rows_used')}")
    if summary.get("gold_rows_used", 0) == 0:
        print("NOTE: Fill human_labels_v1.json criteria decisions to enable comparison")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
