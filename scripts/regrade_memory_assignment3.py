"""Re-grade Memory Game (assignment 3) after deterministic P5 routing fix."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ["WHATSAPP_AUTO_START"] = "false"
os.environ.setdefault("PRO_FAST_PATH", "0")

ASSIGNMENT_ID = 3
STUDENT_NAME = "Memory_Game_Design_Document_COMPLETE"


def _criteria_summary(result: dict) -> list[dict]:
    rows = []
    for cr in result.get("criteria_results") or []:
        rows.append(
            {
                "level": cr.get("criteria_level"),
                "achieved": bool(cr.get("achieved")),
                "score": cr.get("score"),
                "awardable": cr.get("awardable"),
            }
        )
    return rows


async def main() -> None:
    from app.batch_grader import grade_batch_async
    from app.database import SessionLocal
    from app.models import (
        Assignment,
        BatchGrading,
        BatchStatus,
        GradingCriteria,
        GradingSummary,
        Submission,
        SubmissionStatus,
    )

    staging = ROOT / "uploads" / "students" / "bx43"
    docx = staging / f"{STUDENT_NAME}.docx"
    if not docx.is_file():
        raise SystemExit(f"missing primary doc: {docx}")

    paths = sorted(
        {str(p) for p in staging.rglob("*") if p.is_file()},
        key=str.lower,
    )
    has_code = any(p.lower().endswith((".gml", ".yyp", ".yy")) for p in paths)
    has_exe = any(".exe" in p.lower() or p.lower().endswith(".zip") for p in paths)

    db = SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.id == ASSIGNMENT_ID).first()
        if not assignment:
            raise SystemExit(f"assignment {ASSIGNMENT_ID} not found")
        criteria = (
            db.query(GradingCriteria)
            .filter(GradingCriteria.assignment_id == ASSIGNMENT_ID)
            .all()
        )
        grading_criteria = [
            {
                "criteria_level": c.criteria_level,
                "criteria_name": c.criteria_name,
                "criteria_description": c.criteria_description,
                "max_score": c.weight,
            }
            for c in criteria
        ]
        ref = json.loads(assignment.reference_solution_json or "{}")
        user_id = assignment.created_by or 1
    finally:
        db.close()

    student_info = {
        "name": STUDENT_NAME,
        "path": str(docx),
        "email": "",
        "student_id": "",
        "submission_paths": paths,
        "has_code_files": has_code,
        "has_executable_artifacts": has_exe,
    }

    print(f"Re-grading PRO: {len(paths)} files from {staging}")
    results = await grade_batch_async(
        [student_info],
        ref,
        grading_criteria,
        skip_grading_cache=True,
        grading_mode="deep",
        max_workers=1,
    )
    result = results[0] if results else {}
    if not result.get("success"):
        raise SystemExit(f"grading failed: {result.get('error')}")

    det = result.get("deterministic_rubric_engine") or {}
    print(
        "AFTER grade:",
        result.get("grade_level"),
        "pct:",
        result.get("percentage"),
        "inst:",
        result.get("institutional_grade_display"),
    )
    for row in _criteria_summary(result):
        print(f"  {row['level']} ach={row['achieved']} score={row['score']} awardable={row['awardable']}")
    print(
        "det changes:",
        [(c.get("criteria_level"), c.get("action")) for c in det.get("changes") or []],
    )

    db = SessionLocal()
    try:
        batch = BatchGrading(
            assignment_id=ASSIGNMENT_ID,
            batch_name=f"PRO regrade fix إنتاج {datetime.utcnow():%Y-%m-%d %H:%M}",
            total_students=1,
            processed_students=1,
            status=BatchStatus.COMPLETED,
            created_by=user_id,
        )
        db.add(batch)
        db.flush()

        submission = Submission(
            assignment_id=ASSIGNMENT_ID,
            batch_id=batch.id,
            student_name=result["student_name"],
            submission_file_path=result.get("file_path") or str(docx),
            submission_text=result.get("plagiarism_text") or result.get("student_text"),
            submitted_by=user_id,
            status=SubmissionStatus.COMPLETED,
            grading_snapshot_json=json.dumps(result, ensure_ascii=False, default=str),
        )
        db.add(submission)
        db.flush()

        summary = GradingSummary(
            submission_id=submission.id,
            total_score=result.get("total_score", 0),
            max_score=result.get("max_score", 100),
            percentage=result.get("percentage", 0),
            grade_level=result.get("grade_level", "U"),
            overall_feedback=result.get("overall_feedback", ""),
            ai_likelihood=result.get("ai_likelihood", 0),
        )
        db.add(summary)
        db.commit()
        print(f"Saved batch_id={batch.id} submission_id={submission.id}")
        print(f"Results URL: /batch-results/{batch.id}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
