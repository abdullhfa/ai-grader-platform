"""Batch grading API routes (progress, latest batch)."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BatchGrading, BatchStatus
from app.routes.deps import get_batch_progress_dict

router = APIRouter(tags=["grading"])

_ORPHAN_RESTART_MARKERS = (
    "أُعيد تشغيله",
    "أعيد تشغيله",
    "restarted",
)


def _maybe_schedule_checkpoint_resume(request: Request, batch_id: int) -> None:
    """One background resume per batch when UI polls after a server restart."""
    from app.batch_checkpoint import load_batch_checkpoint, resume_batch_from_checkpoint

    triggered = getattr(request.app.state, "_resume_triggered_batch_ids", None)
    if not isinstance(triggered, set):
        triggered = set()
        request.app.state._resume_triggered_batch_ids = triggered
    if batch_id in triggered:
        return
    ck = load_batch_checkpoint(batch_id)
    if not ck or ck.get("paused"):
        return
    triggered.add(batch_id)
    batch_progress = get_batch_progress_dict(request)

    async def _run() -> None:
        await resume_batch_from_checkpoint(ck, batch_progress)

    asyncio.create_task(_run())


@router.get("/api/batch-grade-progress/{assignment_id}")
async def get_batch_progress(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.batch_grade_worker import PHASE_LABELS_AR, _sync_progress_percent

    from app.batch_progress_store import (
        load_assignment_progress,
        sanitize_progress_batch_refs,
    )

    batch_progress = get_batch_progress_dict(request)
    info = batch_progress.get(assignment_id)
    persisted = load_assignment_progress(assignment_id)
    if persisted:
        if info is None:
            info = persisted
            batch_progress[assignment_id] = info
        elif int(persisted.get("start_time") or 0) >= int(info.get("start_time") or 0):
            info.update(persisted)
    if info is not None:
        info = sanitize_progress_batch_refs(assignment_id, info, db)
        batch_progress[assignment_id] = info
        from app.batch_grade_worker import finalize_cancelled_batch_if_stuck

        if finalize_cancelled_batch_if_stuck(batch_progress, assignment_id):
            info = batch_progress.get(assignment_id)
        if info and info.get("paused"):
            pass
        elif info and info.get("resuming") and info.get("batch_id"):
            _maybe_schedule_checkpoint_resume(request, int(info["batch_id"]))
        elif (
            info
            and str(info.get("current_phase") or "") == "queued"
            and not info.get("failed")
            and float(info.get("start_time") or 0) > 0
            and (time.time() - float(info.get("start_time") or 0)) > 180
            and info.get("batch_id")
        ):
            from app.batch_checkpoint import load_batch_checkpoint

            if load_batch_checkpoint(int(info["batch_id"])):
                _maybe_schedule_checkpoint_resume(request, int(info["batch_id"]))
    if info is not None and not info.get("finished"):
        fr = info.get("final_response") if isinstance(info.get("final_response"), dict) else None
        if fr and fr.get("success") and fr.get("batch_id"):
            info["finished"] = True
            info["percent"] = 100
            info["completed"] = max(int(info.get("completed") or 0), int(info.get("total") or 1))
            info["current_phase"] = ""
            batch_progress[assignment_id] = info

    if info is None:
        batch = (
            db.query(BatchGrading)
            .filter(BatchGrading.assignment_id == assignment_id)
            .order_by(BatchGrading.id.desc())
            .first()
        )
        if batch:
            status = (
                batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status)
            )
            if status in (
                BatchStatus.PROCESSING.value,
                BatchStatus.PENDING.value,
                BatchStatus.FAILED.value,
            ):
                from app.batch_checkpoint import (
                    batch_is_resumable_after_restart,
                    load_batch_checkpoint,
                )
                from app.batch_grade_worker import finalize_stale_processing_batch

                if status == BatchStatus.FAILED.value:
                    fail_msg = batch.failure_message or ""
                    if "أُلغي" in fail_msg or "الغاء" in fail_msg:
                        return {"found": False}

                if batch_is_resumable_after_restart(int(batch.id)):
                    ck = load_batch_checkpoint(int(batch.id)) or {}
                    if ck.get("paused"):
                        preflight = dict(ck.get("gamemaker_preflight") or {})
                        toolchain = dict(preflight.get("toolchain") or {})
                        return {
                            "found": True,
                            "completed": int(batch.processed_students or 0),
                            "total": max(
                                int(batch.total_students or 0),
                                len(ck.get("student_files") or []),
                                1,
                            ),
                            "current_student": "",
                            "current_phase": "paused_gamemaker",
                            "phase_label": (
                                "تم إيقاف التصحيح مؤقتاً — ثبّت GameMaker وافتحه "
                                "وسجّل الدخول، ثم اضغط Complete."
                            ),
                            "student_progress": 0.0,
                            "percent": 8,
                            "start_time": float(ck.get("pause_started_at") or 0),
                            "student_times": [],
                            "completed_students": [],
                            "all_student_names": [
                                s.get("name", "")
                                for s in (ck.get("student_files") or [])
                                if isinstance(s, dict)
                            ],
                            "archive_all_files": ck.get("accumulated_archive_files") or [],
                            "archive_student_map": ck.get("accumulated_archive_map") or {},
                            "upload_intake": ck.get("batch_intake_manifest"),
                            "finished": False,
                            "failed": False,
                            "paused": True,
                            "pause_kind": "gamemaker_dependency",
                            "required_dependency": preflight,
                            "download_url": (
                                preflight.get("download_url")
                                or toolchain.get("download_url")
                            ),
                            "error": None,
                            "batch_id": batch.id,
                            "final_response": None,
                        }
                    _maybe_schedule_checkpoint_resume(request, int(batch.id))
                    _ck_archive = bool(ck.get("accumulated_archive_files"))
                    _resume_pct = max(46 if _ck_archive else 8, int(batch.processed_students or 0) * 10)
                    return {
                        "found": True,
                        "completed": int(batch.processed_students or 0),
                        "total": max(
                            int(batch.total_students or 0),
                            len(ck.get("student_files") or [])
                            + len(ck.get("cached_results") or []),
                            1,
                        ),
                        "current_student": "",
                        "current_phase": "grading",
                        "phase_label": "جاري استئناف التصحيح بعد إعادة تشغيل الخادم...",
                        "student_progress": 0.05,
                        "percent": _resume_pct,
                        "start_time": 0,
                        "student_times": [],
                        "completed_students": [],
                        "all_student_names": [
                            s.get("name", "")
                            for s in (ck.get("student_files") or [])
                            if isinstance(s, dict)
                        ],
                        "archive_all_files": ck.get("accumulated_archive_files") or [],
                        "archive_student_map": ck.get("accumulated_archive_map") or {},
                        "upload_intake": ck.get("batch_intake_manifest"),
                        "finished": False,
                        "failed": False,
                        "error": None,
                        "batch_id": batch.id,
                        "final_response": None,
                        "server_restarted": True,
                        "resuming": True,
                    }
                if status in (BatchStatus.PROCESSING.value, BatchStatus.PENDING.value):
                    finalize_stale_processing_batch(batch)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    msg = batch.failure_message or "توقّف التصحيح — أعد المحاولة"
                    return {
                        "found": True,
                        "finished": True,
                        "failed": True,
                        "error": msg,
                        "batch_id": batch.id,
                        "completed": int(batch.processed_students or 0),
                        "total": max(int(batch.total_students or 0), 1),
                        "percent": 0,
                        "current_student": "",
                        "current_phase": "failed",
                        "phase_label": msg,
                        "student_progress": 0,
                        "start_time": 0,
                        "student_times": [],
                        "completed_students": [],
                        "all_student_names": [],
                        "archive_all_files": [],
                        "archive_student_map": {},
                        "upload_intake": None,
                        "final_response": None,
                    }
            if status == BatchStatus.FAILED.value:
                fail_msg = batch.failure_message or ""
                if "أُلغي" in fail_msg or "الغاء" in fail_msg:
                    return {"found": False}
                if any(m in fail_msg for m in _ORPHAN_RESTART_MARKERS):
                    from app.batch_checkpoint import batch_is_resumable_after_restart

                    if batch_is_resumable_after_restart(int(batch.id)):
                        _maybe_schedule_checkpoint_resume(request, int(batch.id))
                        return {
                            "found": True,
                            "finished": False,
                            "failed": False,
                            "error": None,
                            "batch_id": batch.id,
                            "completed": int(batch.processed_students or 0),
                            "total": max(int(batch.total_students or 0), 1),
                            "percent": 5,
                            "current_student": "",
                            "current_phase": "grading",
                            "phase_label": "جاري استئناف التصحيح بعد إعادة تشغيل الخادم...",
                            "student_progress": 0.05,
                            "start_time": 0,
                            "student_times": [],
                            "completed_students": [],
                            "all_student_names": [],
                            "archive_all_files": [],
                            "archive_student_map": {},
                            "upload_intake": None,
                            "final_response": None,
                            "server_restarted": True,
                            "resuming": True,
                        }
                return {
                    "found": True,
                    "finished": True,
                    "failed": True,
                    "error": fail_msg or "توقّف التصحيح — أعد المحاولة",
                    "batch_id": batch.id,
                    "completed": int(batch.processed_students or 0),
                    "total": max(int(batch.total_students or 0), 1),
                    "percent": 0,
                    "current_student": "",
                    "current_phase": "failed",
                    "phase_label": fail_msg or "فشل التصحيح",
                    "student_progress": 0,
                    "start_time": 0,
                    "student_times": [],
                    "completed_students": [],
                    "all_student_names": [],
                    "archive_all_files": [],
                    "archive_student_map": {},
                    "upload_intake": None,
                    "final_response": None,
                }
        return {"found": False}
    _sync_progress_percent(info)
    if info.get("failed"):
        from app.batch_grade_worker import _enrich_batch_failure_response

        fr = info.get("final_response")
        if isinstance(fr, dict):
            _enrich_batch_failure_response(fr)
            info["error"] = fr.get("detail_ar") or fr.get("detail") or info.get("error")
            info["error_code"] = fr.get("error_code")
    phase = info.get("current_phase") or ""
    return {
        "found": True,
        "completed": info["completed"],
        "total": info["total"],
        "current_student": info.get("current_student", ""),
        "current_phase": phase,
        "phase_label": info.get("phase_label") or PHASE_LABELS_AR.get(phase, ""),
        "student_progress": info.get("student_progress", 0),
        "percent": info.get("percent", 0),
        "start_time": info["start_time"],
        "student_times": info["student_times"],
        "completed_students": info.get("completed_students", []),
        "all_student_names": info.get("all_student_names", []),
        "archive_all_files": info.get("archive_all_files", []),
        "archive_student_map": info.get("archive_student_map", {}),
        "upload_intake": info.get("upload_intake"),
        "finished": bool(info.get("finished")),
        "failed": bool(info.get("failed")),
        "error": info.get("error"),
        "error_code": info.get("error_code"),
        "batch_id": info.get("batch_id"),
        "final_response": info.get("final_response"),
        "grading_mode": info.get("grading_mode"),
        "grading_mode_label": info.get("grading_mode_label"),
        "cancel_requested": bool(info.get("cancel_requested")),
        "cancelled": bool(info.get("cancelled")),
        "server_restarted": bool(info.get("server_restarted")),
        "resuming": bool(info.get("resuming")),
        "paused": bool(info.get("paused")),
        "pause_kind": info.get("pause_kind"),
        "required_dependency": info.get("required_dependency"),
        "download_url": (
            info.get("download_url")
            or ((info.get("required_dependency") or {}).get("download_url")
                if isinstance(info.get("required_dependency"), dict) else None)
        ),
    }


@router.post("/api/batch-grade-complete-gamemaker/{assignment_id}")
async def complete_gamemaker_installation(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Recheck GameMaker/Igor, then resume the exact paused checkpoint."""
    from app.batch_checkpoint import (
        load_batch_checkpoint,
        resume_batch_from_checkpoint,
        save_batch_checkpoint,
    )
    from app.batch_progress_store import load_assignment_progress, persist_assignment_progress
    from app.runtime_engines.gamemaker.toolchain import (
        preflight_gamemaker_runtime_dependency,
    )

    batch_progress = get_batch_progress_dict(request)
    info = batch_progress.get(assignment_id) or load_assignment_progress(assignment_id) or {}
    batch_id = int(info.get("batch_id") or 0)
    if not batch_id:
        latest = (
            db.query(BatchGrading)
            .filter(BatchGrading.assignment_id == assignment_id)
            .order_by(BatchGrading.id.desc())
            .first()
        )
        batch_id = int(latest.id) if latest else 0
    checkpoint = load_batch_checkpoint(batch_id) if batch_id else None
    if not checkpoint or not checkpoint.get("paused"):
        raise HTTPException(status_code=404, detail="لا يوجد تصحيح GameMaker متوقف للاستكمال.")

    preflight = await asyncio.to_thread(
        preflight_gamemaker_runtime_dependency,
        list(checkpoint.get("student_files") or []),
    )
    if preflight.get("pause_required"):
        checkpoint["gamemaker_preflight"] = preflight
        save_batch_checkpoint(batch_id, checkpoint)
        info.update(
            {
                "found": True,
                "batch_id": batch_id,
                "paused": True,
                "pause_kind": "gamemaker_dependency",
                "current_phase": "paused_gamemaker",
                "required_dependency": preflight,
                "phase_label": (
                    "لم يكتمل إعداد GameMaker بعد. افتح GameMaker وسجّل الدخول "
                    "وتأكد من تثبيت Windows Runtime، ثم اضغط Complete مرة أخرى."
                ),
                "finished": False,
                "failed": False,
            }
        )
        batch_progress[assignment_id] = info
        persist_assignment_progress(assignment_id, info)
        raise HTTPException(
            status_code=409,
            detail={
                "message": info["phase_label"],
                "preflight": preflight,
                "download_url": preflight.get("download_url"),
            },
        )

    for key in ("paused", "pause_kind", "pause_started_at"):
        checkpoint.pop(key, None)
    checkpoint["gamemaker_preflight"] = preflight
    save_batch_checkpoint(batch_id, checkpoint)

    batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
    if batch:
        batch.status = BatchStatus.PROCESSING  # type: ignore[assignment]
        batch.failure_message = None  # type: ignore[assignment]
        db.commit()

    for key in ("paused", "pause_kind", "required_dependency"):
        info.pop(key, None)
    info.update(
        {
            "batch_id": batch_id,
            "current_phase": "queued",
            "phase_label": "تم العثور على GameMaker — جاري استكمال التصحيح...",
            "resuming": True,
            "finished": False,
            "failed": False,
        }
    )
    batch_progress[assignment_id] = info
    persist_assignment_progress(assignment_id, info)
    triggered = getattr(request.app.state, "_resume_triggered_batch_ids", None)
    if isinstance(triggered, set):
        triggered.discard(batch_id)
    resumed = await resume_batch_from_checkpoint(checkpoint, batch_progress)
    if not resumed:
        raise HTTPException(status_code=500, detail="تعذّر استئناف نقطة التصحيح المحفوظة.")
    return {
        "success": True,
        "resumed": True,
        "batch_id": batch_id,
        "message": "تم العثور على GameMaker واستؤنف التصحيح.",
        "preflight": preflight,
    }


@router.post("/api/batch-grade-reset-progress/{assignment_id}")
async def reset_batch_progress(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Clear in-flight progress/checkpoints so a new upload can start."""
    from app.batch_grade_worker import force_stop_assignment_grading

    batch_progress = get_batch_progress_dict(request)
    result = force_stop_assignment_grading(
        batch_progress,
        assignment_id,
        db,
        reason="أُلغي لرفع ملف جديد",
        clear_staging=True,
    )
    return {
        "success": True,
        "assignment_id": assignment_id,
        **result,
    }


@router.post("/api/batch-grade-cancel/{assignment_id}")
async def cancel_batch_grading(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stop/clear in-progress or post-restart resuming batch grading."""
    from app.batch_grade_worker import force_stop_assignment_grading

    batch_progress = get_batch_progress_dict(request)
    result = force_stop_assignment_grading(batch_progress, assignment_id, db)
    return {"success": True, "message": "تم إيقاف التصحيح", **result}


@router.get("/api/batch-meta/{batch_id}")
async def get_batch_meta(batch_id: int, db: Session = Depends(get_db)):
    """Lightweight check before redirecting UI to /batch-results/{id}."""
    from app.batch_checkpoint import (
        ensure_batch_row_from_checkpoint,
        load_batch_checkpoint,
    )

    batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
    if not batch:
        ck = load_batch_checkpoint(batch_id)
        if ck:
            batch = ensure_batch_row_from_checkpoint(ck, db)
    if not batch:
        return {"found": False, "batch_id": batch_id}
    status = batch.status.value if hasattr(batch.status, "value") else str(batch.status)
    return {
        "found": True,
        "batch_id": batch.id,
        "assignment_id": batch.assignment_id,
        "status": status,
        "processed_students": batch.processed_students,
        "total_students": batch.total_students,
    }


@router.get("/api/batch-grade-latest/{assignment_id}")
async def get_latest_batch_for_assignment(assignment_id: int, db: Session = Depends(get_db)):
    batch = (
        db.query(BatchGrading)
        .filter(BatchGrading.assignment_id == assignment_id)
        .order_by(BatchGrading.id.desc())
        .first()
    )
    if not batch:
        return {"found": False}
    status = batch.status.value if hasattr(batch.status, "value") else str(batch.status)
    return {
        "found": True,
        "batch_id": batch.id,
        "status": status,
        "processed_students": batch.processed_students,
        "total_students": batch.total_students,
        "failure_message": batch.failure_message or "",
    }
