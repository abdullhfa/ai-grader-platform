"""Repair stored submissions: finalize criteria + sync GradingResult rows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import GradingResult, GradingSummary, Submission
from app.criteria_result_finalizer import (
    finalize_grading_criteria_results,
    sync_criteria_results_to_db,
)


def repair_student(db, *, name_contains: str) -> int:
    subs = (
        db.query(Submission)
        .filter(Submission.student_name.ilike(f"%{name_contains}%"))
        .order_by(Submission.id.desc())
        .all()
    )
    fixed = 0
    for sub in subs:
        raw = getattr(sub, "grading_snapshot_json", None)
        if not raw:
            print(f"skip #{sub.id} {sub.student_name}: no snapshot")
            continue
        try:
            snap = json.loads(str(raw))
        except json.JSONDecodeError:
            print(f"skip #{sub.id}: bad json")
            continue
        if not snap.get("criteria_results"):
            print(f"skip #{sub.id}: no criteria_results")
            continue
        before = {
            str(c.get("criteria_level")): (c.get("achieved"), c.get("score"))
            for c in snap.get("criteria_results") or []
            if "P5" in str(c.get("criteria_level", "")) or "P6" in str(c.get("criteria_level", ""))
        }
        fin = finalize_grading_criteria_results(
            snap, artifact_inventory=snap.get("artifact_inventory")
        )
        sub.grading_snapshot_json = json.dumps(snap, ensure_ascii=False)
        sync = sync_criteria_results_to_db(db, sub.id, snap)
        db.commit()
        after = {
            str(c.get("criteria_level")): (c.get("achieved"), c.get("score"))
            for c in snap.get("criteria_results") or []
            if "P5" in str(c.get("criteria_level", "")) or "P6" in str(c.get("criteria_level", ""))
        }
        print(
            f"#{sub.id} {sub.student_name}: changes={fin.get('change_count')} "
            f"sync={sync} P5/P6 {before} -> {after}"
        )
        fixed += 1
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="ahmad hamtini", help="Student name substring")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        n = repair_student(db, name_contains=args.name)
        print(f"Repaired {n} submission(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
