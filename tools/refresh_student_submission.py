"""Refresh explainability + optional L4 runtime for one submission (no full AI re-grade)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh submission snapshot explainability/runtime")
    parser.add_argument("--submission-id", type=int, default=1)
    parser.add_argument("--student-name", type=str, default="")
    parser.add_argument("--rerun-runtime", action="store_true", help="Re-run L4 sandbox (Godot pairing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.explainability_migration import backfill_submission_record
    from app.models import Submission

    db = SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == args.submission_id).first()
        if not sub and args.student_name:
            sub = (
                db.query(Submission)
                .filter(Submission.student_name.ilike(f"%{args.student_name}%"))
                .order_by(Submission.id.desc())
                .first()
            )
        if not sub:
            print(json.dumps({"error": "submission not found"}, ensure_ascii=False))
            return

        report = backfill_submission_record(
            sub,
            db=db,
            dry_run=args.dry_run,
            force=True,
            rerun_runtime=args.rerun_runtime,
            trigger="tools.refresh_student_submission",
            generated_by="tools/refresh_student_submission",
        )
        if report.get("applied") and not args.dry_run:
            db.commit()

        snap = json.loads(str(sub.grading_snapshot_json or "{}"))
        inst = snap.get("institutional_resolution") or {}
        obs = (snap.get("artifact_inventory") or {}).get("runtime_observation_report") or {}
        out = {
            "report": report,
            "student_name": sub.student_name,
            "institutional_display": inst.get("display_grade_ar"),
            "runtime_engine": obs.get("engine"),
            "runtime_status": obs.get("status"),
            "runtime_observed": obs.get("runtime_observed"),
            "screenshots": len(obs.get("runtime_screenshots") or []),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
