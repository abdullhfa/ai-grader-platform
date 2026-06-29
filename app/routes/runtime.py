"""Runtime replay, L4 gate, and playtest routes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_id
from app.database import get_db
from app.models import Submission
from app.routes.deps import app_title, get_templates, load_grading_snapshot, orm_set
from app.services.subscription import get_subscription_info

router = APIRouter(tags=["runtime"])


class RuntimeSessionRequest(BaseModel):
    submission_id: Optional[int] = None
    root_path: str = Field(..., description="Submission root directory or entry file")
    student_name: str = ""
    async_mode: bool = False
    paths: Optional[List[str]] = None


@router.post("/api/runtime/sessions")
async def create_runtime_session_api(req: RuntimeSessionRequest):
    """Start an L4 runtime observation session (sync or Celery async)."""
    root = Path(req.root_path)
    if not root.exists():
        raise HTTPException(status_code=404, detail="root_path not found")

    paths = req.paths
    if not paths:
        if root.is_file():
            paths = [str(root)]
        else:
            paths = [str(p) for p in root.rglob("*") if p.is_file()][:200]

    if req.async_mode:
        from app.tasks.celery_app import is_celery_enabled
        from app.tasks.worker_tasks import runtime_observation_task

        if not is_celery_enabled():
            raise HTTPException(
                status_code=503,
                detail="Celery not enabled — set AI_GRADER_CELERY_ENABLED=1",
            )
        task = runtime_observation_task.delay(
            paths,
            submission_id=req.submission_id,
            student_name=req.student_name,
        )
        return {"status": "queued", "task_id": task.id}

    from app.runtime.sandbox_engine import run_sandbox_observation

    result = run_sandbox_observation(
        paths,
        submission_id=req.submission_id,
        student_name=req.student_name,
        enable_smoke_test=True,
    )
    return result


@router.post("/api/runtime/web/launch")
async def launch_web_runtime_api(req: RuntimeSessionRequest):
    """Headless launch for HTML5/web game projects."""
    from app.runtime_engines.web.playwright_runner import find_web_entry_point, run_web_game_headless

    root = Path(req.root_path)
    entry = find_web_entry_point(root)
    if not entry:
        raise HTTPException(status_code=404, detail="No HTML entry point found")

    shot_dir = Path(f"uploads/runtime_sessions/{req.student_name or 'web'}/screenshots")
    return run_web_game_headless(entry, screenshot_dir=shot_dir)


class UnityBuildRequest(BaseModel):
    project_path: str = Field(..., description="Unity project root (contains Assets/ and ProjectSettings/)")
    student_name: str = ""
    output_name: str = "game.exe"
    async_mode: bool = False
    run_playmode_tests: bool = False


@router.post("/api/runtime/unity/build")
async def unity_build_api(req: UnityBuildRequest):
    """Run Unity headless Windows build (and optional Play Mode tests)."""
    from app.runtime_engines.unity.build_runner import (
        UnityBuildConfig,
        resolve_unity_binary,
        run_unity_build,
    )
    from app.runtime_engines.unity.playmode_runner import maybe_run_playmode_tests
    from app.runtime_engines.unity.project_probe import find_unity_project_root

    project_root = find_unity_project_root(Path(req.project_path))
    if not project_root:
        raise HTTPException(status_code=404, detail="Unity project not found")

    if req.async_mode:
        from app.tasks.celery_app import is_celery_enabled
        from app.tasks.worker_tasks import unity_build_task

        if not is_celery_enabled():
            raise HTTPException(status_code=503, detail="Celery not enabled")
        task = unity_build_task.delay(
            str(project_root),
            req.student_name,
            req.output_name,
            req.run_playmode_tests,
        )
        return {"status": "queued", "task_id": task.id, "project_root": str(project_root)}

    unity_bin = resolve_unity_binary()
    if not unity_bin:
        raise HTTPException(
            status_code=503,
            detail="Unity binary not configured — set AI_GRADER_UNITY_BIN",
        )

    workspace = Path(f"uploads/runtime_sessions/{req.student_name or 'unity'}")
    workspace.mkdir(parents=True, exist_ok=True)
    build_result = run_unity_build(
        UnityBuildConfig(
            project_path=project_root,
            unity_path=unity_bin,
            output_exe=workspace / "build" / req.output_name,
            log_path=workspace / "unity_build.log",
        )
    )
    response: Dict[str, Any] = {"build": build_result, "project_root": str(project_root)}

    if req.run_playmode_tests:
        response["playmode"] = maybe_run_playmode_tests(project_root, workspace)

    if build_result.get("artifact"):
        from app.runtime_observation_sandbox import observe_unity_windows_exe

        response["smoke_test"] = observe_unity_windows_exe(Path(str(build_result["artifact"])))

    return response


@router.post("/api/runtime/unity/smoke")
async def unity_smoke_api(req: RuntimeSessionRequest):
    """Run Unity-aware smoke test on an existing Windows build."""
    from app.runtime_engines.unity.project_probe import find_unity_executable
    from app.runtime_observation_sandbox import observe_unity_windows_exe

    root = Path(req.root_path)
    executable = find_unity_executable(root)
    if not executable:
        raise HTTPException(status_code=404, detail="Unity executable not found")
    return observe_unity_windows_exe(executable)


@router.get("/api/runtime/l4-gate-status")
async def runtime_l4_gate_status_api():
    from app.governance_freeze_registry import get_l4_gate_status

    return get_l4_gate_status()


@router.get("/api/runtime-replay/{submission_id}")
async def runtime_replay_api(submission_id: int, db: Session = Depends(get_db)):
    from app.runtime_replay_viewer import build_runtime_replay

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    snap = load_grading_snapshot(submission)
    return build_runtime_replay(
        snap,
        student_name=getattr(submission, "student_name", "") or "",
        batch_id=getattr(submission, "batch_id", None),
        submission_id=submission_id,
    )


@router.get("/runtime-replay/{submission_id}", response_class=HTMLResponse)
async def runtime_replay_page(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    from app.runtime_replay_viewer import build_runtime_replay
    from app.submission_playtest import get_submission_playtest_state

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    snap = load_grading_snapshot(submission)
    replay = build_runtime_replay(
        snap,
        student_name=getattr(submission, "student_name", "") or "",
        batch_id=getattr(submission, "batch_id", None),
        submission_id=submission_id,
    )
    playtest = get_submission_playtest_state(submission_id, snap)
    user = get_current_user(request, db)
    user_id = get_current_user_id(request)
    sub_info = get_subscription_info(db, user_id) if user_id else None
    templates = get_templates(request)
    return templates.TemplateResponse(
        "runtime_replay.html",
        {
            "request": request,
            "user": user,
            "app_title": app_title(),
            "submission": submission,
            "replay": replay,
            "playtest": playtest,
            "subscription": sub_info,
        },
    )


@router.get("/api/playtest/{submission_id}")
async def playtest_state_api(submission_id: int, db: Session = Depends(get_db)):
    from app.submission_playtest import get_submission_playtest_state

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return get_submission_playtest_state(submission_id, load_grading_snapshot(submission))


@router.post("/api/playtest/{submission_id}/start")
async def playtest_start_api(submission_id: int, db: Session = Depends(get_db)):
    from app.submission_playtest import start_submission_playtest

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    record = start_submission_playtest(
        submission_id,
        student_name=getattr(submission, "student_name", "") or "",
        grading_snapshot=load_grading_snapshot(submission),
    )
    return {"status": "started", "pass": record}


@router.post("/api/playtest/{submission_id}/record")
async def playtest_record_api(
    submission_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.submission_playtest import record_submission_playtest_observation

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    body = await request.json()
    pass_id = str(body.get("pass_id") or "")
    test_id = str(body.get("test_id") or "")
    observed_en = str(body.get("observed_en") or "").strip()
    if not pass_id or not test_id or not observed_en:
        raise HTTPException(status_code=400, detail="pass_id, test_id, observed_en required")
    try:
        record = record_submission_playtest_observation(
            submission_id,
            pass_id,
            test_id,
            observed_en=observed_en,
            status=str(body.get("status") or "observed"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "recorded", "pass": record}


@router.post("/api/playtest/{submission_id}/finalize")
async def playtest_finalize_api(
    submission_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.submission_playtest import finalize_submission_playtest

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    body = await request.json()
    pass_id = str(body.get("pass_id") or "")
    if not pass_id:
        raise HTTPException(status_code=400, detail="pass_id required")
    try:
        result = finalize_submission_playtest(
            submission_id, pass_id, grading_snapshot=load_grading_snapshot(submission) or {}
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    updated_snapshot = result["grading_snapshot"]
    apply_to_grades = body.get("apply_to_grades", True)
    db_sync = None
    if apply_to_grades:
        from app.submission_runtime_adjudication import sync_runtime_adjudication_to_db

        db_sync = sync_runtime_adjudication_to_db(
            db, submission, updated_snapshot, require_human_playtest=True
        )
        if db_sync.get("applied"):
            updated_snapshot = load_grading_snapshot(submission) or updated_snapshot
        else:
            orm_set(submission, "grading_snapshot_json", json.dumps(updated_snapshot, ensure_ascii=False))
            db.commit()
    else:
        orm_set(submission, "grading_snapshot_json", json.dumps(updated_snapshot, ensure_ascii=False))
        db.commit()

    try:
        from app.academic_event_replay import append_playtest_finalize_events

        append_playtest_finalize_events(
            updated_snapshot, playtest_result=result.get("pass"), db_sync=db_sync
        )
        orm_set(submission, "grading_snapshot_json", json.dumps(updated_snapshot, ensure_ascii=False))
        db.commit()
    except Exception:
        pass

    return {
        "status": "finalized",
        "pass": result["pass"],
        "runtime_criterion_support": updated_snapshot.get("runtime_criterion_support"),
        "l5_human_playtest": updated_snapshot.get("l5_human_playtest"),
        "db_sync": db_sync,
    }


@router.post("/api/submission/{submission_id}/apply-runtime-adjudication")
async def apply_runtime_adjudication_api(
    submission_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.submission_runtime_adjudication import sync_runtime_adjudication_to_db

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    body: Dict[str, Any] = {}
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()
    except Exception:
        body = {}
    grading_snapshot = load_grading_snapshot(submission)
    if not grading_snapshot:
        raise HTTPException(status_code=400, detail="No grading_snapshot on submission")
    result = sync_runtime_adjudication_to_db(
        db,
        submission,
        grading_snapshot,
        require_human_playtest=bool(body.get("require_human_playtest", True)),
    )
    if not result.get("applied"):
        raise HTTPException(status_code=409, detail=result.get("message_ar") or result.get("reason"))
    return result
