#!/usr/bin/env python3
"""Run STEP 3 controlled runtime cohort and write JSON report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.calibration.runtime_cohort.runner import run_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description="STEP 3 — Real Runtime Cohort")
    parser.add_argument(
        "--config",
        default=str(ROOT / "app/calibration/runtime_cohort/cohort_config_v1.json"),
        help="Cohort config JSON",
    )
    parser.add_argument(
        "--human-labels",
        default=str(ROOT / "app/calibration/human_labels_v1.json"),
        help="Human grade labels JSON",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output report path (default: app/calibration/runtime_cohort/reports/)",
    )
    parser.add_argument(
        "--submission-id",
        type=int,
        action="append",
        dest="submission_ids",
        help="Limit to specific DB submission(s); skips path fixtures",
    )
    parser.add_argument(
        "--batch-id",
        type=int,
        help="Run runtime cohort for all submissions in a batch (skips config fixtures)",
    )
    parser.add_argument(
        "--no-runtime",
        action="store_true",
        help="Skip live sandbox probes — snapshot/replay metrics only",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    human_path = Path(args.human_labels) if args.human_labels else None

    if args.batch_id:
        from app.calibration.runtime_cohort.runner import run_cohort_for_batch

        report = run_cohort_for_batch(
            args.batch_id,
            run_runtime=not args.no_runtime,
            human_labels_path=human_path if human_path and human_path.exists() else None,
        )
    else:
        report = run_cohort(
            config_path,
            ROOT,
            run_runtime=not args.no_runtime,
            human_labels_path=human_path if human_path and human_path.exists() else None,
            submission_ids=args.submission_ids,
            fixtures_only=args.fixtures_only,
        )

    if args.out:
        out_path = Path(args.out)
    else:
        reports_dir = ROOT / "app/calibration/runtime_cohort/reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = report.get("generated_at", "run").replace(":", "").replace("-", "")
        out_path = reports_dir / f"cohort_{ts}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report.get("summary") or {}
        print(f"Cohort report: {out_path}")
        print(f"Entries: {report.get('entry_count')}")
        print(f"Replay stable: {summary.get('deterministic_replay_stable_count')}")
        print(f"Replay unstable: {summary.get('deterministic_replay_unstable')}")
        print(f"Runtime launched: {summary.get('runtime_actually_launched')}")
        print(f"Files-only detection: {summary.get('files_only_detection')}")
        flags = summary.get("priority_flags") or {}
        if flags.get("replay_hash_unstable"):
            print("WARNING: replay hash instability — reducer non-deterministic")
        if flags.get("replay_verification_mismatch"):
            print("WARNING: replay hash stable but snapshot verification failed")
        if flags.get("runtime_not_executed"):
            print("WARNING: executable detected but sandbox did not run")
        if flags.get("human_labels_missing"):
            print("NOTE: human labels not filled — fill human_labels_v1.json for divergence")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
