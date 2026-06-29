"""Run one PRO re-grade for Jana and print vision/runtime diagnostics."""
from __future__ import annotations

import asyncio
import json
import os
import sys
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
    from app.models import Assignment, GradingCriteria

    student_root = ROOT / "uploads" / "students" / "bx10" / "Jana Dwiri U8 L3"
    if not student_root.is_dir():
        for p in (ROOT / "uploads" / "students").rglob("Jana Dwiri U8 L3"):
            if p.is_dir():
                student_root = p
                break

    paths = sorted({str(p) for p in student_root.rglob("*") if p.is_file()}, key=str.lower)
    aim_c = next((p for p in paths if p.lower().endswith("aim c.docx")), paths[0] if paths else "")

    db = SessionLocal()
    try:
        assignment = db.query(Assignment).filter(Assignment.id == 1).first()
        if not assignment:
            raise SystemExit("assignment 1 not found")
        criteria = (
            db.query(GradingCriteria)
            .filter(GradingCriteria.assignment_id == assignment.id)
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
    finally:
        db.close()

    student_info = {
        "name": "جنى عصام الدويري",
        "path": aim_c,
        "email": "",
        "student_id": "",
        "submission_paths": paths,
        "has_code_files": any(p.lower().endswith((".gml", ".yyp")) for p in paths),
        "has_executable_artifacts": any(p.lower().endswith(".exe") for p in paths),
    }

    print(f"Grading {len(paths)} files, doc={Path(aim_c).name}")
    results = await grade_batch_async(
        [student_info],
        ref,
        grading_criteria,
        skip_grading_cache=True,
        grading_mode="deep",
        max_workers=1,
    )
    r = results[0] if results else {}
    inv = r.get("artifact_inventory") or {}
    ves = inv.get("visual_evidence_summary") or r.get("visual_evidence_summary") or {}
    obs = inv.get("runtime_observation_report") or {}
    print("success", r.get("success"), "grade", r.get("grade_level"), r.get("percentage"))
    print("vision", {k: ves.get(k) for k in ("vision_status", "vision_error", "images_analyzed", "images_submitted")})
    print("runtime", {k: obs.get(k) for k in ("status", "runtime_verified", "runtime_observed", "engine")})


if __name__ == "__main__":
    asyncio.run(main())
