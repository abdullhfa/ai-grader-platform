#!/usr/bin/env python3
"""
Institutional Validation Pipeline — closes operational phases after engineering.

Read-only on grades. Runs:
  1. Seed human_labels (PENDING + AI hints)
  2. Export system snapshots
  3. Runtime cohort (batch coverage)
  4. Calibration + disagreement + Cohen's Kappa
  5. Key test suites
  6. Governance release metrics update
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "app/calibration/reports"
LABELS = ROOT / "app/calibration/human_labels_v1.json"
GOVERNANCE = ROOT / "app/calibration/governance_release_v1.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_unittest(module_path: str) -> dict:
    proc = subprocess.run(
        [sys.executable, module_path],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Institutional validation pipeline")
    parser.add_argument("--batch-id", type=int, default=5, help="Latest pilot batch")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--no-runtime", action="store_true", help="Skip live sandbox probes")
    args = parser.parse_args()

    from app.calibration.disagreement_report import build_disagreement_report
    from app.calibration.human_labels_io import export_system_snapshots_from_db, seed_human_label_records
    from app.calibration.runtime_cohort.runner import run_cohort_for_batch
    from app.database import SessionLocal
    from app.models import BatchGrading, Submission

    REPORTS.mkdir(parents=True, exist_ok=True)
    run_id = f"institutional_validation_{_utc_now().replace(':', '')}"

    db = SessionLocal()
    try:
        batch = db.query(BatchGrading).filter(BatchGrading.id == args.batch_id).first()
        subs = (
            db.query(Submission)
            .filter(Submission.batch_id == args.batch_id)
            .order_by(Submission.id)
            .all()
        )
        sub_ids = [1] + [int(s.id) for s in subs]
    finally:
        db.close()

    steps: dict = {}

    # 1 — Human labels scaffold
    seed = seed_human_label_records(LABELS, submission_ids=sub_ids)
    steps["human_labels_seed"] = seed

    # 2 — System snapshots
    systems_path = REPORTS / "system_snapshots_latest.json"
    export_system_snapshots_from_db(sub_ids, systems_path)
    steps["system_snapshots"] = {"path": str(systems_path), "submission_ids": sub_ids}

    # 3 — Runtime cohort
    cohort_report = run_cohort_for_batch(
        args.batch_id,
        run_runtime=not args.no_runtime,
        replay_trials=3,
        human_labels_path=LABELS,
    )
    cohort_path = REPORTS / f"batch{args.batch_id}_runtime_coverage.json"
    cohort_path.write_text(json.dumps(cohort_report, ensure_ascii=False, indent=2), encoding="utf-8")
    steps["runtime_cohort"] = {
        "path": str(cohort_path),
        "summary": cohort_report.get("summary"),
    }

    # 4 — Calibration / disagreement
    disagreement = build_disagreement_report(
        human_labels_path=LABELS,
        systems_path=systems_path,
        cohort_report_path=cohort_path,
        run_id=run_id,
    )
    disagreement_path = REPORTS / "disagreement_latest.json"
    disagreement_path.write_text(json.dumps(disagreement, ensure_ascii=False, indent=2), encoding="utf-8")
    steps["calibration"] = {
        "path": str(disagreement_path),
        "summary": disagreement.get("summary"),
    }

    # 5 — Tests
    if not args.skip_tests:
        steps["tests_http_e2e"] = _run_unittest("tests/test_http_e2e.py")
        steps["tests_replay"] = _run_unittest("tests/test_replay_determinism.py")
        steps["tests_cohort"] = _run_unittest("tests/test_runtime_cohort.py")

    # 6 — Stress battery
    if not args.skip_stress:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools/run_stress_battery.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        steps["stress_battery"] = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1500:],
        }

    # 7 — Institutional summary
    cohort_sum = cohort_report.get("summary") or {}
    cal_sum = disagreement.get("summary") or {}
    replay_stable = cohort_sum.get("deterministic_replay_stable_count", 0)
    entry_count = cohort_report.get("entry_count", 0)
    runtime_launched = len(cohort_sum.get("runtime_actually_launched") or [])
    files_only = len(cohort_sum.get("files_only_detection") or [])

    institutional = {
        "report_type": "institutional_validation_v1",
        "generated_at": _utc_now(),
        "run_id": run_id,
        "batch_id": args.batch_id,
        "batch_status": batch.status.value if batch and hasattr(batch.status, "value") else None,
        "engineering_phases": "closed",
        "institutional_phases": "in_progress",
        "metrics": {
            "submissions_in_cohort": entry_count,
            "replay_stable_count": replay_stable,
            "replay_stable_rate": round(replay_stable / max(entry_count, 1), 4),
            "runtime_launched_count": runtime_launched,
            "files_only_detection_count": files_only,
            "calibration_gold_rows": cal_sum.get("gold_rows_used"),
            "agreement_rate": cal_sum.get("agreement_rate"),
            "cohens_kappa": cal_sum.get("cohens_kappa"),
            "criterion_mismatches": cal_sum.get("criterion_mismatch_count"),
            "replay_mismatches": cal_sum.get("replay_mismatch_count"),
        },
        "phase_status": {
            "architecture": "closed",
            "runtime_sandbox": "closed",
            "replay_determinism": "closed",
            "calibration_infrastructure": "closed",
            "stress_testing": "closed" if steps.get("stress_battery", {}).get("ok") else "pending",
            "observability": "closed",
            "governance_freeze": "pre_pilot",
            "http_e2e": "closed" if steps.get("tests_http_e2e", {}).get("ok") else "pending",
            "runtime_cohort": "closed",
            "human_labels": "scaffolded_pending_teacher",
            "pilot_moderation": "pending",
            "cohens_kappa_full": "partial" if cal_sum.get("cohens_kappa") is not None else "pending_labels",
        },
        "institutional_honesty_ar": (
            "Presence ≠ Authority — runtime launch 0/N expected for source-only batch; "
            "P5/P6 withheld without runnable build."
        ),
        "steps": steps,
    }

    out_path = REPORTS / "institutional_validation_latest.json"
    out_path.write_text(json.dumps(institutional, ensure_ascii=False, indent=2), encoding="utf-8")

    # 8 — Update governance release metrics (non-freeze)
    if GOVERNANCE.exists():
        gov = json.loads(GOVERNANCE.read_text(encoding="utf-8"))
        gov["calibration_run_id"] = run_id
        gov["calibration_metrics"] = {
            "agreement_rate": cal_sum.get("agreement_rate"),
            "cohens_kappa": cal_sum.get("cohens_kappa"),
            "false_positive_rate": (disagreement.get("calibration") or {}).get("metrics", {}).get(
                "false_positive_rate"
            ),
            "replay_verification_rate": institutional["metrics"]["replay_stable_rate"],
            "runtime_success_rate": round(runtime_launched / max(entry_count, 1), 4),
            "note_ar": "يُحدَّث تلقائياً — pilot freeze يتطلب توقيع مؤسسي",
        }
        GOVERNANCE.write_text(json.dumps(gov, ensure_ascii=False, indent=2), encoding="utf-8")
        steps["governance_release"] = str(GOVERNANCE)

    print(f"Institutional validation: {out_path}")
    print(f"Batch #{args.batch_id} replay stable: {replay_stable}/{entry_count}")
    print(f"Runtime launched: {runtime_launched}/{entry_count}")
    print(f"Gold rows (teacher labels): {cal_sum.get('gold_rows_used')}")
    print(f"Agreement rate: {cal_sum.get('agreement_rate')}")
    print(f"Cohen's Kappa: {cal_sum.get('cohens_kappa')}")
    if cal_sum.get("gold_rows_used", 0) < 9:
        print("NOTE: Fill teacher decisions in human_labels_v1.json for full Kappa")

    all_tests_ok = all(
        steps.get(k, {}).get("ok", True)
        for k in ("tests_http_e2e", "tests_replay", "tests_cohort", "stress_battery")
    )
    return 0 if all_tests_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
