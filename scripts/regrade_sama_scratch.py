"""Re-grade Sama's Scratch submission (verifies game-artifact path fallback fix)."""
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

    student_root = ROOT / "uploads" / "students" / "bx48"
    paths = sorted({str(p) for p in student_root.rglob("*") if p.is_file()}, key=str.lower)
    main_doc = next((p for p in paths if p.lower().endswith((".docx", ".doc"))), paths[0])

    db = SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.id == 1).first()
        if not assignment:
            raise SystemExit("assignment 1 not found")
        criteria = (
            db.query(GradingCriteria).filter(GradingCriteria.assignment_id == assignment.id).all()
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
        user_id = 1
    finally:
        db.close()

    student_info = {
        "name": "Sama Ziad AlRahahleh",
        "path": main_doc,
        "email": "",
        "student_id": "",
        "submission_paths": paths,
        "has_code_files": True,
        "has_executable_artifacts": True,
    }

    print("Files:", *[Path(p).name for p in paths], sep="\n  ")
    print("Running PRO grade...")
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
        print("FAILED", result.get("error"))
        return

    db = SessionLocal()
    try:
        batch = BatchGrading(
            assignment_id=1,
            batch_name=f"Sama Scratch regrade {datetime.utcnow():%Y-%m-%d %H:%M}",
            total_students=1,
            processed_students=1,
            status=BatchStatus.COMPLETED,
            created_by=user_id,
        )
        db.add(batch)
        db.flush()

        submission = Submission(
            assignment_id=1,
            batch_id=batch.id,
            student_name=result["student_name"],
            submission_file_path=result.get("file_path"),
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

        print(f"\n=== batch_id={batch.id} submission_id={submission.id} ===")
        print("GRADE:", result.get("grade_level"), "| criteria_score_pct:", result.get("criteria_score_pct"))
        for c in result.get("criteria_results") or []:
            print(
                f"  {c.get('criteria_level'):8} achieved={c.get('achieved')} "
                f"awardable={c.get('awardable')}"
            )
        gov = result.get("btec_criteria_governance") or {}
        print("GOV changes:", gov.get("changes"))
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
