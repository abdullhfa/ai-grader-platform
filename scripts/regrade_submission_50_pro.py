"""PRO re-grade submission 50 (Ahmad Bakr) — double-run stability check."""

from __future__ import annotations



import asyncio

import json

import os

import sys

from pathlib import Path

from typing import Any



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))

os.chdir(ROOT)



from dotenv import load_dotenv



load_dotenv(override=True)

os.environ["WHATSAPP_AUTO_START"] = "false"

os.environ.setdefault("PRO_FAST_PATH", "0")



SUBMISSION_ID = 50

RUNS = 2

PASS_LEVELS = ("B.P3", "B.P4", "C.P5", "C.P6")





def _criteria_summary(result: dict) -> list[dict]:

    rows = []

    for cr in result.get("criteria_results") or []:

        rows.append(

            {

                "level": cr.get("criteria_level"),

                "achieved": bool(cr.get("achieved")),

                "awardable": cr.get("awardable"),

                "runtime_gate_block": cr.get("runtime_gate_block"),

                "score": cr.get("score"),

                "authority": cr.get("achievement_authority"),

            }

        )

    return rows





def _key_criteria(result: dict) -> dict[str, bool]:

    out: dict[str, bool] = {}

    for cr in result.get("criteria_results") or []:

        if not isinstance(cr, dict):

            continue

        level = str(cr.get("criteria_level") or "")

        short = level.split(".")[-1] if "." in level else level

        for target in PASS_LEVELS:

            if level == target or short == target.split(".")[-1]:

                out[target] = bool(cr.get("achieved"))

    return out





def _gameplay_summary(result: dict) -> dict:

    inv = result.get("artifact_inventory") or {}

    gv = (

        inv.get("gameplay_verification")

        or result.get("gameplay_verification")

        or (inv.get("runtime_observation_report") or {}).get("gameplay_verification")

        or {}

    )

    gate = result.get("runtime_evidence_gate") or {}

    alg = gate.get("automated_l4_gate") or {}

    return {

        "gameplay_entered": gv.get("gameplay_entered"),

        "l4_level": gv.get("l4_level") or gv.get("automated_l4_level"),

        "player_movement_verified": gv.get("player_movement_verified"),

        "mechanics_verified_count": gv.get("mechanics_verified_count"),

        "criterion_pass": alg.get("criterion_pass") or {},

        "runtime_gate_status": gate.get("runtime_status"),

        "grade_level": result.get("grade_level"),

    }





def _resolve_submission_paths(sub: Any, snap: dict) -> list[str]:

    """Collect on-disk paths; fall back when DB points at missing bx55 folder."""

    candidates: list[str] = []

    for key in ("submission_paths", "intake_relative_paths"):

        candidates.extend(str(p) for p in (snap.get(key) or []) if p)

    if sub.submission_file_path:

        candidates.append(str(sub.submission_file_path))

        candidates.append(str(Path(str(sub.submission_file_path)).parent))



    paths = sorted({str(p) for p in candidates if p and Path(str(p)).is_file()}, key=str.lower)

    if paths:

        return paths



    root = Path("uploads/students")

    if root.is_dir():

        folder = root / "bx72" / "Ahmad Bakr Hatem Abu Shaira TF(77644)  هدف (ب+ج)"

        if folder.is_dir():

            return sorted({str(p) for p in folder.rglob("*") if p.is_file()}, key=str.lower)

        for exe in root.rglob("P_03.exe"):

            return sorted({str(p) for p in exe.parent.rglob("*") if p.is_file()}, key=str.lower)

    return []





def _build_finalize_inventory(result: dict) -> dict:

    """Prefer full gameplay inventory for terminal gate (slim snapshot may omit fields)."""

    inv = dict(result.get("artifact_inventory") or {})

    gv = result.get("gameplay_verification")

    if isinstance(gv, dict) and gv:

        inv["gameplay_verification"] = gv

    paths = result.get("submission_paths") or result.get("intake_relative_paths")

    if paths:

        inv.setdefault("submission_paths", paths)

        inv.setdefault("intake_relative_paths", paths)

    return inv





async def _grade_once(

    student_info: dict,

    ref: dict,

    grading_criteria: list[dict],

    run_index: int,

) -> dict:

    from app.batch_grader import grade_batch_async

    from app.btec_criteria_governance import ensure_clean_grading_result_feedback

    from app.criteria_result_finalizer import finalize_grading_criteria_results



    print(f"\n========== RUN {run_index}/{RUNS} ==========")

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

        raise SystemExit(f"run {run_index} failed: {result.get('error')}")



    finalize_grading_criteria_results(

        result,

        artifact_inventory=_build_finalize_inventory(result),

    )

    ensure_clean_grading_result_feedback(result)



    gameplay = _gameplay_summary(result)

    print("=== GAMEPLAY SUMMARY ===")

    print(json.dumps(gameplay, ensure_ascii=False, indent=2))

    print("=== CRITERIA ===")

    for row in _criteria_summary(result):

        print(row)

    print(f"grade_level={result.get('grade_level')} total_score={result.get('total_score')}")

    return result





def _save_to_db(result: dict, sub: Any, criteria: list) -> None:

    from app.btec_criteria_governance import teacher_facing_feedback

    from app.core.grading_profiles import attach_grading_mode_metadata
    from app.grading_mode_policy import compact_snapshot_for_storage

    from app.criteria_result_finalizer import sync_criteria_results_to_db

    from app.database import SessionLocal

    from app.models import GradingResult, GradingSummary, Submission



    snap_out = attach_grading_mode_metadata(

        compact_snapshot_for_storage({k: v for k, v in result.items() if k != "student_text"}, "deep"),

        "deep",

    )



    db = SessionLocal()

    try:

        sub_row = db.query(Submission).filter(Submission.id == SUBMISSION_ID).first()

        if not sub_row:

            raise SystemExit("submission vanished")

        sub_row.grading_snapshot_json = json.dumps(snap_out, ensure_ascii=False, default=str)



        criteria_level_to_id: dict[str, int] = {}

        for c in criteria:

            criteria_level_to_id[str(c.criteria_level)] = int(c.id)

            if "." in str(c.criteria_level):

                criteria_level_to_id[str(c.criteria_level).split(".")[-1]] = int(c.id)



        db.query(GradingResult).filter(GradingResult.submission_id == SUBMISSION_ID).delete()

        for cr in snap_out.get("criteria_results") or []:

            if not isinstance(cr, dict):

                continue

            level = str(cr.get("criteria_level") or "")

            cid = criteria_level_to_id.get(level) or 0

            if cid == 0 and "." in level:

                cid = criteria_level_to_id.get(level.split(".")[-1], 0)

            db.add(

                GradingResult(

                    submission_id=SUBMISSION_ID,

                    criteria_id=cid or (criteria[0].id if criteria else 0),

                    achieved=bool(cr.get("achieved")),

                    score=int(cr.get("score") or 0),

                    max_score=100,

                    missing_points=json.dumps(cr.get("missing_points") or [], ensure_ascii=False),

                    feedback=teacher_facing_feedback(str(cr.get("feedback") or "")),

                    next_level_requirements=json.dumps(

                        cr.get("next_level_requirements") or [], ensure_ascii=False

                    ),

                )

            )



        summary = (

            db.query(GradingSummary).filter(GradingSummary.submission_id == SUBMISSION_ID).first()

        )

        if summary:

            summary.total_score = int(snap_out.get("total_score") or 0)

            summary.max_score = int(snap_out.get("max_score") or 100)

            summary.percentage = float(snap_out.get("percentage") or 0)

            summary.grade_level = str(snap_out.get("grade_level") or "U")

            summary.overall_feedback = str(snap_out.get("overall_feedback") or "")

        else:

            db.add(

                GradingSummary(

                    submission_id=SUBMISSION_ID,

                    total_score=int(snap_out.get("total_score") or 0),

                    max_score=int(snap_out.get("max_score") or 100),

                    percentage=float(snap_out.get("percentage") or 0),

                    grade_level=str(snap_out.get("grade_level") or "U"),

                    overall_feedback=str(snap_out.get("overall_feedback") or ""),

                )

            )



        sync_criteria_results_to_db(db, SUBMISSION_ID, snap_out)

        db.commit()

        print(f"Saved submission {SUBMISSION_ID} — grade={snap_out.get('grade_level')}")

        print(f"UI: /results/{SUBMISSION_ID}")

    finally:

        db.close()





async def main() -> None:

    from app.database import SessionLocal

    from app.models import Assignment, GradingCriteria, Submission



    db = SessionLocal()

    try:

        sub = db.query(Submission).filter(Submission.id == SUBMISSION_ID).first()

        if not sub:

            raise SystemExit(f"submission {SUBMISSION_ID} not found")

        assignment = db.query(Assignment).filter(Assignment.id == sub.assignment_id).first()

        if not assignment:

            raise SystemExit("assignment not found")

        criteria = (

            db.query(GradingCriteria)

            .filter(GradingCriteria.assignment_id == sub.assignment_id)

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

        snap = json.loads(str(sub.grading_snapshot_json or "{}"))

        paths = _resolve_submission_paths(sub, snap)

        primary = str(sub.submission_file_path or (paths[0] if paths else ""))

        if paths and (not primary or not Path(primary).is_file()):

            primary = next(

                (p for p in paths if p.lower().endswith((".docx", ".pdf", ".exe"))),

                paths[0],

            )

        has_exe = any(str(p).lower().endswith(".exe") for p in paths)

        has_code = any(

            str(p).lower().endswith((".gd", ".gml", ".cs", ".tscn"))

            for p in paths

        )

        student_name = sub.student_name

        batch_id = sub.batch_id

    finally:

        db.close()



    student_info = {

        "name": student_name,

        "path": primary,

        "email": "",

        "student_id": "",

        "submission_paths": paths,

        "submission_id": SUBMISSION_ID,

        "batch_id": batch_id,

        "has_code_files": has_code,

        "has_executable_artifacts": has_exe,

    }



    print(f"PRO double re-grade submission {SUBMISSION_ID}: {len(paths)} files")

    run_results: list[dict] = []

    for i in range(1, RUNS + 1):

        run_results.append(await _grade_once(student_info, ref, grading_criteria, i))



    keys_r1 = _key_criteria(run_results[0])

    keys_r2 = _key_criteria(run_results[1])

    print("\n========== STABILITY CHECK ==========")

    print(f"Run 1 criteria: {keys_r1} grade={run_results[0].get('grade_level')}")

    print(f"Run 2 criteria: {keys_r2} grade={run_results[1].get('grade_level')}")



    stable = keys_r1 == keys_r2

    all_pass = all(keys_r2.get(k) for k in PASS_LEVELS) and run_results[1].get("grade_level") == "P"

    print(f"B.P3/B.P4 stable across runs: {stable}")

    print(f"Pass-band + grade P on run 2: {all_pass}")



    _save_to_db(run_results[-1], sub, criteria)



    if not stable or not all_pass:

        raise SystemExit(1)





if __name__ == "__main__":

    asyncio.run(main())

