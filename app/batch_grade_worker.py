"""
Background batch grading — avoids HTTP timeout (Failed to fetch) on long AI runs.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from app.core.grading_pipeline import run_batch_grading
from app.batch_grader import (  # type: ignore
    check_plagiarism_for_submission,
)
from app.database import SessionLocal  # type: ignore
from app import models  # type: ignore
from app.models import (  # type: ignore
    BatchGrading,
    BatchStatus,
    GradingCriteria,
    GradingResult,
    GradingSummary,
    StudentReport,
    Submission,
    SubmissionStatus,
)
from app.report_generator import (  # type: ignore
    generate_batch_summary_report,
    generate_student_report_pdf,
)
from app.grading_snapshot_governance import (  # type: ignore
    attach_governance_to_payload,
    reconcile_canonical_drift_for_assignment,
)
from app.archive_extraction_utils import hash_submission_file
from app.grading_mode_policy import (
    compact_snapshot_for_storage,
    grading_mode_display_label,
    normalize_grading_mode_choice,
    resolve_grading_policy,
)

REPORTS_DIR = Path("uploads") / "reports"

PHASE_LABELS_AR = {
    "queued": "في قائمة انتظار التصحيح على الخادم...",
    "starting": "جاري تحضير التصحيح...",
    "preparing": "جاري تحضير الملفات...",
    "extracting_archive": "جاري فك الملف المضغوط (ZIP/RAR)...",
    "extracting": "استخراج محتوى ملف الطالب...",
    "vision": "تحليل الصور واللقطات...",
    "runtime": "تشغيل اللعبة والتحقق التشغيلي (GameMaker/EXE)...",
    "inventory": "فحص المشروع والأدلة التقنية...",
    "grading": "المقيم الذكي يصحّح المعايير...",
    "finalizing": "التحقق المؤسسي وحوكمة BTEC (Pearson)...",
    "saving": "حفظ النتائج...",
    "cancelling": "جاري إيقاف التصحيح...",
    "cancelled": "تم إيقاف التصحيح",
}


def _clone_graded_submission(
    db,
    source_sub: Submission,
    *,
    batch_id: int,
    assignment_id: int,
    user_id: int,
) -> Submission:
    """Copy a previously graded submission into a new batch with identical scores."""
    snap = source_sub.grading_snapshot_json
    if snap:
        try:
            snap_obj = json.loads(snap)
            snap_obj["cached_from_submission_id"] = source_sub.id
            snap_obj["cached"] = True
            snap = json.dumps(snap_obj, ensure_ascii=False)
        except Exception:
            pass

    new_sub = Submission(
        assignment_id=assignment_id,
        batch_id=batch_id,
        student_name=source_sub.student_name,
        student_email=source_sub.student_email or "",
        submission_file_path=source_sub.submission_file_path,
        submission_text=source_sub.submission_text,
        submitted_by=user_id,
        status=SubmissionStatus.COMPLETED,
        grading_snapshot_json=snap,
    )
    db.add(new_sub)
    db.flush()

    for src_result in (
        db.query(GradingResult).filter(GradingResult.submission_id == source_sub.id).all()
    ):
        db.add(
            GradingResult(
                submission_id=new_sub.id,
                criteria_id=src_result.criteria_id,
                achieved=src_result.achieved,
                score=src_result.score,
                max_score=src_result.max_score,
                missing_points=src_result.missing_points,
                feedback=src_result.feedback,
                next_level_requirements=src_result.next_level_requirements,
            )
        )

    src_summary = (
        db.query(GradingSummary)
        .filter(GradingSummary.submission_id == source_sub.id)
        .first()
    )
    if src_summary:
        db.add(
            GradingSummary(
                submission_id=new_sub.id,
                total_score=src_summary.total_score,
                max_score=src_summary.max_score,
                percentage=src_summary.percentage,
                ai_likelihood=src_summary.ai_likelihood,
                plagiarism_max_similarity=src_summary.plagiarism_max_similarity,
                plagiarism_suspicious_count=src_summary.plagiarism_suspicious_count,
                overall_feedback=src_summary.overall_feedback,
                strengths=src_summary.strengths,
                improvements=src_summary.improvements,
                grade_level=src_summary.grade_level,
            )
        )

    src_report = (
        db.query(StudentReport)
        .filter(StudentReport.submission_id == source_sub.id)
        .first()
    )
    report_path = REPORTS_DIR / f"report_{new_sub.id}.pdf"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if src_report and src_report.report_file_path:
        src_pdf = Path(str(src_report.report_file_path))
        if src_pdf.is_file():
            shutil.copy2(src_pdf, report_path)
            db.add(
                StudentReport(
                    submission_id=new_sub.id,
                    report_file_url=f"/uploads/reports/report_{new_sub.id}.pdf",
                    report_file_path=str(report_path),
                )
            )
    elif snap:
        try:
            snap_obj = json.loads(snap) if isinstance(snap, str) else snap
            if isinstance(snap_obj, dict) and snap_obj.get("grade_level"):
                generate_student_report_pdf(
                    str(new_sub.student_name or ""),
                    str(new_sub.student_email or ""),
                    snap_obj,
                    str(report_path),
                )
                db.add(
                    StudentReport(
                        submission_id=new_sub.id,
                        report_file_url=f"/uploads/reports/report_{new_sub.id}.pdf",
                        report_file_path=str(report_path),
                    )
                )
        except Exception as pdf_exc:
            print(
                f"⚠️ [PDF-CACHE-CLONE] report skipped for submission #{new_sub.id}: {pdf_exc}"
            )

    db.commit()
    return new_sub


def _grading_percent_floor(info: Dict[str, Any]) -> int:
    """Minimum UI percent for the current phase — prevents drops after archive/PRO band."""
    phase = str(info.get("current_phase") or "")
    prev = int(info.get("percent") or 0)
    sp = max(0.0, min(0.99, float(info.get("student_progress") or 0)))
    if phase == "preparing":
        return prev
    if phase == "extracting_archive":
        return max(prev, 8)
    if phase == "queued":
        return max(prev, 8)
    if phase == "extracting" and sp < 0.30:
        return max(prev, 12)
    if phase in (
        "grading", "vision", "runtime", "inventory", "saving", "starting",
    ):
        try:
            deep = normalize_grading_mode_choice(str(info.get("grading_mode") or "deep")) == "deep"
        except Exception:
            deep = True
        if deep and info.get("archive_all_files"):
            return max(prev, 46)
        if phase in ("grading", "vision", "runtime", "inventory", "saving"):
            return max(prev, 12)
    return prev


def _sync_progress_percent(info: Dict[str, Any]) -> None:
    total = max(int(info.get("total") or 0), 1)
    completed = min(float(info.get("completed") or 0), float(total))
    info["completed"] = int(completed)
    sp = max(0.0, min(0.99, float(info.get("student_progress") or 0)))
    phase = str(info.get("current_phase") or "")
    floor = _grading_percent_floor(info)

    if phase in ("grading", "vision", "runtime", "inventory", "saving", "extracting") and total <= 1:
        band_top = 98
        if floor >= 46:
            computed = min(band_top, floor + round(sp * max(band_top - floor, 1)))
        else:
            computed = min(99, round(((completed + sp) / total) * 100))
    else:
        computed = min(99, round(((completed + sp) / total) * 100))

    prev = int(info.get("percent") or 0)
    early_work = phase in (
        "queued",
        "starting",
        "preparing",
        "extracting_archive",
        "extracting",
    ) and sp < 0.30
    if early_work:
        info["percent"] = max(computed, 8 if phase in ("queued", "starting") else 12)
    else:
        info["percent"] = max(prev, computed, floor)
    if (
        int(completed) < total
        and phase in ("grading", "vision", "runtime", "inventory")
        and not info.get("finished")
    ):
        info["percent"] = min((info["percent"]), 85)
    if int(completed) >= total and not info.get("finished"):
        info["percent"] = max(info["percent"], 99)


def _commit_progress(batch_progress: dict, assignment_id: int, info: Dict[str, Any]) -> None:
    """Mirror in-memory progress to disk so UI/API stay in sync."""
    try:
        from app.batch_progress_store import touch_batch_progress

        touch_batch_progress(batch_progress, assignment_id)
    except Exception:
        pass


def _finalize_batch_cancelled(
    batch_progress: dict,
    assignment_id: int,
    *,
    batch_id: int | None = None,
    detail: str = "أُوقف التصحيح قبل إكمال أي طالب",
) -> None:
    """Mark progress finished when cancel wins but the worker exits early (queued/stale)."""
    info = _progress_entry(batch_progress, assignment_id)
    if info.get("finished"):
        return
    bid = batch_id or info.get("batch_id")
    completed = int(info.get("completed") or 0)
    total = max(int(info.get("total") or 0), 1)
    if completed > 0:
        detail = (
            f"أُوقف التصحيح يدوياً — اكتمل {completed} من {total} طالب"
        )
    info.update(
        {
            "finished": True,
            "failed": completed == 0,
            "cancelled": True,
            "cancel_requested": True,
            "current_phase": "cancelled",
            "phase_label": PHASE_LABELS_AR["cancelled"],
            "current_student": "",
            "student_progress": 0.0,
            "percent": 100 if completed > 0 else max(int(info.get("percent") or 0), 12),
            "final_response": {
                "success": completed > 0,
                "cancelled": True,
                "detail": detail,
                "batch_id": bid,
                "processed": completed,
                "total_students": total,
            },
        }
    )
    batch_progress[assignment_id] = info
    _commit_progress(batch_progress, assignment_id, info)
    print(f"⏹️ [BATCH-CANCEL] finalized assignment={assignment_id} batch={bid}")


def finalize_cancelled_batch_if_stuck(
    batch_progress: dict,
    assignment_id: int,
    *,
    max_wait_seconds: float = 90.0,
) -> bool:
    """Safety net: if cancel was requested but no worker finished, close the UI loop."""
    info = batch_progress.get(assignment_id)
    if not info or info.get("finished") or not info.get("cancel_requested"):
        return False
    cancel_at = float(info.get("cancel_requested_at") or info.get("start_time") or 0)
    if not cancel_at or (time.time() - cancel_at) < max_wait_seconds:
        return False
    _finalize_batch_cancelled(
        batch_progress,
        assignment_id,
        batch_id=int(info["batch_id"]) if info.get("batch_id") else None,
        detail="أُوقف التصحيح — انتهت مهلة انتظار إيقاف العامل",
    )
    return True


def force_stop_assignment_grading(
    batch_progress: dict,
    assignment_id: int,
    db: Any,
    *,
    reason: str = "أُلغي — إيقاف التصحيح يدوياً",
    clear_staging: bool = False,
) -> Dict[str, Any]:
    """
    Stop/clear an in-flight or post-restart «resuming» batch.

    ``clear_staging=False`` (cancel button): stop the job without deleting extracted
    files mid-grade — avoids corrupting an in-flight worker and «Failed to fetch» on
    the next upload. ``clear_staging=True`` (reset / new upload): wipe staging too.
    """
    from app.batch_checkpoint import (
        clear_staging_for_assignment,
        pause_all_checkpoints_for_assignment,
    )

    ensure_assignment_progress_loaded(batch_progress, assignment_id)
    info = batch_progress.get(assignment_id)
    if info and not info.get("finished"):
        request_batch_cancel(batch_progress, assignment_id)

    _bump_assignment_job_generation(assignment_id)

    paused = pause_all_checkpoints_for_assignment(assignment_id)
    cleared = clear_staging_for_assignment(assignment_id, db) if clear_staging else 0

    active = (
        db.query(BatchGrading)
        .filter(
            BatchGrading.assignment_id == assignment_id,
            BatchGrading.status.in_([BatchStatus.PROCESSING, BatchStatus.PENDING]),
        )
        .all()
    )
    for batch in active:
        finalize_stale_processing_batch(batch, message=reason)
    if active:
        db.commit()

    release_assignment_batch_lock(batch_progress, assignment_id)

    return {
        "ok": True,
        "paused_checkpoints": paused,
        "cleared_staging": cleared,
        "cancelled_batches": len(active),
    }


def _public_batch_failure_message(final_response: Dict[str, Any]) -> str:
    """Prefer the first per-student error over the generic ZIP/archive hint."""
    errors = final_response.get("errors") or []
    if errors and isinstance(errors[0], dict):
        specific = str(errors[0].get("error") or "").strip()
        if specific:
            return specific
    detail = str(final_response.get("detail") or "").strip()
    if detail:
        return detail
    return "لم يُصحَّح أي طالب — تحقق من ملف ZIP/RAR أو محتوى التسليم."


def _batch_error_code(message: str) -> str:
    low = (message or "").lower()
    if "429" in low or "depleted" in low or "resource_exhausted" in low:
        return "AI-429"
    if "402" in low or "insufficient" in low or "quota" in low:
        return "AI-402"
    if "json serializable" in low or "windowspath" in low:
        return "SYS-JSON"
    if "timeout" in low or "timed out" in low:
        return "NET-TIMEOUT"
    if "connection" in low or "connect" in low:
        return "NET-CONN"
    return "GRD-001"


def _humanize_batch_error_ar(message: str, *, student: str = "") -> str:
    low = (message or "").lower()
    prefix = f"{student}: " if student else ""
    if "429" in low or "depleted" in low or "resource_exhausted" in low:
        return (
            prefix
            + "نفد رصيد مزود الذكاء الاصطناعي (Gemini). "
            "شحن الحساب من Google AI Studio ثم أعد المحاولة."
        )
    if "402" in low or "insufficient" in low or "quota" in low:
        return prefix + "رصيد الذكاء الاصطناعي غير كافٍ — راجع الفوترة ثم أعد المحاولة."
    if "json serializable" in low or "windowspath" in low:
        return prefix + "خطأ داخلي في النظام أثناء حفظ نتيجة التصحيح — أعد المحاولة بعد تحديث الخادم."
    if "timeout" in low or "timed out" in low:
        return prefix + "انتهت مهلة الاتصال بمزود الذكاء الاصطناعي — أعد المحاولة."
    if "ollama" in low or (
        "connection" in low and (os.getenv("AI_PROVIDER") or "").strip().lower() == "ollama"
    ):
        return (
            prefix
            + "فشل الاتصال بـ Ollama — افتح تطبيق Ollama من شريط المهام (أيقونة الألمة) "
            "ثم نفّذ: ollama run "
            + (os.getenv("OLLAMA_MODEL") or "qwen3:8b")
        )
    if "فشل الاتصال بمزود ai" in low or "openai" in low or "gemini" in low or "anthropic" in low:
        return prefix + (message or "فشل الاتصال بمزود الذكاء الاصطناعي.")
    if "لم يُصحَّح أي طالب" in (message or ""):
        return (
            prefix
            + "لم يُكتمل تصحيح أي طالب. تحقق من محتوى الملف أو راجع رسالة الخطأ التفصيلية أدناه."
        )
    return prefix + (message or "فشل التصحيح — سبب غير معروف.")


def _enrich_batch_failure_response(final_response: Dict[str, Any]) -> Dict[str, Any]:
    raw = _public_batch_failure_message(final_response)
    errors = final_response.get("errors") or []
    student = ""
    if errors and isinstance(errors[0], dict):
        student = str(errors[0].get("student") or "")
    final_response["detail"] = raw
    final_response["error_code"] = _batch_error_code(raw)
    final_response["detail_ar"] = _humanize_batch_error_ar(raw, student=student)
    return final_response


def _progress_entry(batch_progress: dict, assignment_id: int) -> Dict[str, Any]:
    info = batch_progress.get(assignment_id)
    if info is None:
        info = {}
        batch_progress[assignment_id] = info
    return info


def is_batch_cancel_requested(batch_progress: dict, assignment_id: int) -> bool:
    info = batch_progress.get(assignment_id)
    return bool(info and info.get("cancel_requested"))


def request_batch_cancel(batch_progress: dict, assignment_id: int) -> Dict[str, Any]:
    """Ask the background grader to stop after the current student(s)."""
    info = batch_progress.get(assignment_id)
    if not info:
        return {"ok": False, "reason": "not_found"}
    if info.get("finished"):
        return {"ok": False, "reason": "already_finished"}
    info["cancel_requested"] = True
    info["cancel_requested_at"] = time.time()
    info["current_phase"] = "cancelling"
    info["phase_label"] = PHASE_LABELS_AR["cancelling"]
    info["student_progress"] = float(info.get("student_progress") or 0)
    _bump_assignment_job_generation(assignment_id)
    batch_progress[assignment_id] = info
    _commit_progress(batch_progress, assignment_id, info)
    print(f"⏹️ [BATCH-CANCEL] requested assignment={assignment_id} batch={info.get('batch_id')}")
    return {"ok": True, "batch_id": info.get("batch_id")}


def _normalize_selected_criteria(
    selected: List[str],
    grading_criteria: List[Dict],
) -> List[str]:
    """Use all assignment criteria when UI defaults (P1,P2,M1,D1) mismatch BTEC levels."""
    raw = [s.strip() for s in (selected or []) if s.strip()]
    if not raw:
        return []
    db_levels: set[str] = set()
    db_shorts: set[str] = set()
    for c in grading_criteria or []:
        lv = str(c.get("criteria_level") or "")
        if lv:
            db_levels.add(lv)
            db_shorts.add(lv.split(".")[-1] if "." in lv else lv)
    if any("8/" in lv for lv in db_levels):
        return []
    matched = any(s in db_levels or s in db_shorts for s in raw)
    if not matched:
        return []
    return raw


_GRADING_THREAD_POOL = None
_ASSIGNMENT_JOB_GEN: Dict[int, int] = {}


def _bump_assignment_job_generation(assignment_id: int) -> int:
    """Invalidate in-flight workers when a new batch supersedes the prior one."""
    gen = _ASSIGNMENT_JOB_GEN.get(assignment_id, 0) + 1
    _ASSIGNMENT_JOB_GEN[assignment_id] = gen
    return gen


def _assignment_job_is_current(assignment_id: int, generation: int) -> bool:
    return _ASSIGNMENT_JOB_GEN.get(assignment_id, 0) == generation


def _grading_executor():
    global _GRADING_THREAD_POOL
    if _GRADING_THREAD_POOL is None:
        import concurrent.futures

        _max = 2
        try:
            _max = max(2, int(os.getenv("BATCH_GRADING_WORKERS", "2")))
        except ValueError:
            _max = 2
        _GRADING_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_max, 4),
            thread_name_prefix="batch_grader",
        )
    return _GRADING_THREAD_POOL


def _prime_grading_progress_before_queue(job_kwargs: Dict[str, Any]) -> None:
    """Avoid 0% UI stall while the single grading worker thread starts."""
    batch_progress = job_kwargs.get("batch_progress")
    assignment_id = job_kwargs.get("assignment_id")
    batch_id = job_kwargs.get("batch_id")
    if not isinstance(batch_progress, dict) or not isinstance(assignment_id, int):
        return
    info = batch_progress.get(assignment_id) or {}
    if info.get("finished"):
        return
    info["batch_id"] = batch_id
    has_archive = bool(info.get("archive_all_files"))
    info["current_phase"] = "queued"
    info["phase_label"] = PHASE_LABELS_AR["queued"]
    info["percent"] = max(int(info.get("percent") or 0), 8)
    info["student_progress"] = 0.02
    info["start_time"] = time.time()
    batch_progress[assignment_id] = info
    _commit_progress(batch_progress, assignment_id, info)


def schedule_batch_grading_job(**job_kwargs: Any) -> None:
    """Run grading off the HTTP event loop so restarts/resume do not freeze the site."""
    import asyncio as _asyncio

    assignment_id = job_kwargs.get("assignment_id")
    batch_id = job_kwargs.get("batch_id")
    if isinstance(assignment_id, int):
        passed_gen = job_kwargs.get("job_generation")
        if passed_gen is not None:
            _ASSIGNMENT_JOB_GEN[assignment_id] = int(passed_gen)
        else:
            job_kwargs["job_generation"] = _bump_assignment_job_generation(assignment_id)
    if isinstance(assignment_id, int) and isinstance(batch_id, int):
        try:
            from app.batch_checkpoint import delete_superseded_checkpoints_for_assignment

            removed = delete_superseded_checkpoints_for_assignment(
                assignment_id, keep_batch_id=batch_id
            )
            if removed:
                print(
                    f"🗑️ [BATCH-CHECKPOINT] removed {removed} superseded checkpoint(s) "
                    f"for assignment={assignment_id}"
                )
        except Exception:
            pass

    _prime_grading_progress_before_queue(job_kwargs)

    def _runner() -> None:
        _aid = job_kwargs.get("assignment_id")
        _bid = job_kwargs.get("batch_id")
        _gen = job_kwargs.get("job_generation")
        print(
            f"▶️ [BATCH BG] worker start assignment={_aid} batch={_bid} gen={_gen}"
        )
        try:
            _asyncio.run(run_batch_grading_job(**job_kwargs))
        except Exception as exc:
            import traceback as _tb

            print(f"❌ [BATCH BG] worker crashed assignment={_aid} batch={_bid}: {exc}")
            print(_tb.format_exc())

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        _runner()
        return
    loop.run_in_executor(_grading_executor(), _runner)


async def run_batch_grading_job(
    *,
    batch_progress: dict,
    assignment_id: int,
    batch_id: int,
    batch_name: str,
    student_files: List[Dict],
    cached_results: List[Dict],
    grading_criteria: List[Dict],
    selected_criteria_list: List[str],
    reference_solution: Dict,
    batch_intake_manifest: Dict,
    user_id: int,
    subject_bal_id: Optional[int],
    sub_id: Optional[int],
    grading_mode: str = "deep",
    skip_grading_cache: bool = False,
    job_generation: int | None = None,
) -> None:
    from app.strict_grading_policy import skip_grading_cache_default

    if skip_grading_cache_default():
        skip_grading_cache = True

    await asyncio.sleep(0)

    _job_gen = (
        job_generation
        if job_generation is not None
        else _ASSIGNMENT_JOB_GEN.get(assignment_id, 0)
    )

    def _job_stale() -> bool:
        return not _assignment_job_is_current(assignment_id, _job_gen)

    if is_batch_cancel_requested(batch_progress, assignment_id):
        _finalize_batch_cancelled(batch_progress, assignment_id, batch_id=batch_id)
        return
    if _job_stale():
        print(
            f"⏭️ [BATCH BG] stale worker skipped assignment={assignment_id} "
            f"batch={batch_id} gen={_job_gen} current={_ASSIGNMENT_JOB_GEN.get(assignment_id)}"
        )
        if is_batch_cancel_requested(batch_progress, assignment_id):
            _finalize_batch_cancelled(batch_progress, assignment_id, batch_id=batch_id)
        return

    prog = _progress_entry(batch_progress, assignment_id)
    prog.setdefault("finished", False)
    prog.setdefault("failed", False)
    prog["batch_id"] = batch_id
    _grade_total = max(int(prog.get("total") or 0), len(student_files) + len(cached_results), 1)
    prog["total"] = _grade_total
    if not prog.get("current_phase") or prog.get("current_phase") == "queued":
        prog["current_phase"] = "starting"
        prog["phase_label"] = PHASE_LABELS_AR["starting"]
        prog["student_progress"] = 0.02
        _sync_progress_percent(prog)
        _commit_progress(batch_progress, assignment_id, prog)

    db = SessionLocal()
    results: List[Dict] = []
    try:
        batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
        if not batch:
            raise RuntimeError(f"Batch {batch_id} not found")

        criteria = (
            db.query(GradingCriteria)
            .filter(GradingCriteria.assignment_id == assignment_id)
            .all()
        )

        def on_student_start(student_name: str):
            info = batch_progress.get(assignment_id)
            if not info or info.get("batch_id") != batch_id:
                return
            info["current_student"] = student_name
            info["current_phase"] = "extracting"
            info["student_progress"] = 0.08
            _sync_progress_percent(info)
            _commit_progress(batch_progress, assignment_id, info)

        def on_student_phase(student_name: str, phase: str, student_progress: float):
            info = batch_progress.get(assignment_id)
            if not info or info.get("batch_id") != batch_id:
                return
            info["current_student"] = student_name
            info["current_phase"] = phase
            info["phase_label"] = PHASE_LABELS_AR.get(phase, info.get("phase_label") or "")
            info["student_progress"] = max(0.0, min(0.99, student_progress))
            _sync_progress_percent(info)
            _commit_progress(batch_progress, assignment_id, info)

        def on_student_done(student_name: str, success: bool):
            info = batch_progress.get(assignment_id)
            if not info or info.get("batch_id") != batch_id:
                return
            total = max(int(info.get("total") or 0), 1)
            if int(info.get("completed") or 0) < total:
                info["completed"] = int(info.get("completed") or 0) + 1
            info.setdefault("student_times", []).append(
                time.time() - info.get("start_time", time.time())
            )
            info["current_student"] = ""
            info["current_phase"] = ""
            info["student_progress"] = 0.0
            if student_name and student_name not in (info.get("completed_students") or []):
                info.setdefault("completed_students", []).append(student_name)
            _sync_progress_percent(info)
            _commit_progress(batch_progress, assignment_id, info)

        if not student_files and not cached_results:
            raise RuntimeError(
                "لم يُستخرج أي ملف طالب من التسليم (تحقق من ZIP/RAR أو محتوى الأرشيف)."
            )

        explicit_mode = (
            normalize_grading_mode_choice(grading_mode) if grading_mode else None
        )
        policy = resolve_grading_policy(None)
        if sub_id is not None:
            try:
                sub_row = (
                    db.query(models.Subscription)
                    .filter(models.Subscription.id == sub_id)
                    .first()
                )
                if sub_row:
                    pkg = (
                        db.query(models.Package)
                        .filter(models.Package.id == sub_row.package_id)
                        .first()
                    )
                    policy = resolve_grading_policy(pkg.name if pkg else None)
            except Exception:
                policy = resolve_grading_policy(None)
        elif explicit_mode:
            policy = resolve_grading_policy(
                "basic" if explicit_mode == "fast" else "pro"
            )
        prog["grading_mode"] = policy.get("grading_mode", "deep")
        prog["grading_mode_label"] = grading_mode_display_label(
            prog["grading_mode"]
        )

        if student_files:
            from app.ai_provider import ensure_ollama_ready_for_grading

            if is_batch_cancel_requested(batch_progress, assignment_id) or _job_stale():
                _finalize_batch_cancelled(batch_progress, assignment_id, batch_id=batch_id)
                return
            ensure_ollama_ready_for_grading()
            _sel = _normalize_selected_criteria(selected_criteria_list, grading_criteria)

            try:
                from app.evidence_drift_audit import prior_anchor_from_snapshot

                for sf in student_files:
                    sname = str(sf.get("name") or "")
                    if not sname:
                        continue
                    prev_sub = (
                        db.query(Submission)
                        .filter(
                            Submission.assignment_id == assignment_id,
                            Submission.student_name == sname,
                            Submission.grading_snapshot_json.isnot(None),
                        )
                        .order_by(Submission.id.desc())
                        .first()
                    )
                    if prev_sub and prev_sub.grading_snapshot_json:
                        prev_snap = json.loads(prev_sub.grading_snapshot_json)
                        prev_snap["submission_id"] = prev_sub.id
                        anchor = prior_anchor_from_snapshot(prev_snap)
                        if anchor:
                            sf["prior_evidence_anchor"] = anchor
            except Exception as _pa_err:
                print(f"⚠️ [PRIOR-ANCHOR] skipped: {_pa_err}")

            def _cancel_check() -> bool:
                return (
                    is_batch_cancel_requested(batch_progress, assignment_id)
                    or _job_stale()
                )

            results = await run_batch_grading(
                student_files,
                reference_solution,
                grading_criteria,
                selected_criteria=_sel,
                grading_mode=policy.get("grading_mode") or "deep",
                max_retries=policy.get("max_retries"),
                progress_callback=on_student_done,
                start_callback=on_student_start,
                phase_callback=on_student_phase,
                skip_grading_cache=skip_grading_cache,
                cancel_check=_cancel_check,
            )
            if is_batch_cancel_requested(batch_progress, assignment_id) or _cancel_check():
                prog["cancelled"] = True
                print(f"⏹️ [BATCH BG] Cancel requested — assignment {assignment_id}")
        else:
            print("✅ [CACHE] All students already graded - no AI calls needed")

        _pi = batch_progress.get(assignment_id)
        if _pi:
            _pi["current_phase"] = "saving"
            _pi["phase_label"] = PHASE_LABELS_AR["saving"]
            _pi["student_progress"] = 0.95
            _sync_progress_percent(_pi)
            _commit_progress(batch_progress, assignment_id, _pi)

        criteria_level_to_id: Dict[str, int] = {}
        for c in criteria:
            level = cast(str, c.criteria_level)
            criteria_id = cast(int, c.id)
            criteria_level_to_id[level] = criteria_id
            if "." in level:
                criteria_level_to_id[level.split(".")[-1]] = criteria_id

        for result in results:
            if result.get("cancelled"):
                continue
            if not result.get("success", False):
                err_text = str(result.get("error") or "فشل تصحيح هذا الطالب")
                failed_sub = Submission(
                    assignment_id=assignment_id,
                    batch_id=batch.id,
                    student_name=result.get("student_name") or "طالب",
                    student_email=result.get("student_email", ""),
                    submission_file_path=result.get("file_path"),
                    submitted_by=user_id,
                    status=SubmissionStatus.FAILED,
                    grading_snapshot_json=json.dumps(
                        {"success": False, "error": err_text},
                        ensure_ascii=False,
                    ),
                )
                db.add(failed_sub)
                continue
            if "total_score" not in result or "percentage" not in result:
                continue
            if not result.get("grade_level"):
                continue

            submission = Submission(
                assignment_id=assignment_id,
                batch_id=batch.id,
                student_name=result["student_name"],
                student_email=result.get("student_email", ""),
                submission_file_path=result["file_path"],
                submission_text=result.get("plagiarism_text") or result.get("student_text"),
                submitted_by=user_id,
                status=SubmissionStatus.COMPLETED,
            )
            db.add(submission)
            db.flush()

            try:
                from app.criteria_result_finalizer import (
                    finalize_grading_criteria_results,
                    sync_criteria_results_to_db,
                )

                finalize_grading_criteria_results(
                    result,
                    artifact_inventory=result.get("artifact_inventory"),
                )
            except Exception as _pre_db_fin:
                print(f"⚠️ [CRITERIA-FINALIZER] pre-save skipped: {_pre_db_fin}")

            try:
                from app.btec_criteria_governance import ensure_clean_grading_result_feedback

                _cleaned = ensure_clean_grading_result_feedback(result)
                if _cleaned:
                    print(
                        f"🧹 [FEEDBACK-SANITIZE] {result.get('student_name')}: "
                        f"{len(_cleaned)} criterion note(s) cleaned"
                    )
            except Exception as _san_err:
                print(f"⚠️ [FEEDBACK-SANITIZE] skipped: {_san_err}")

            from app.btec_criteria_governance import teacher_facing_feedback

            for criteria_result in result.get("criteria_results", []):
                missing_pts = criteria_result.get(
                    "missing_points",
                    criteria_result.get("next_level_requirements", []),
                )
                cr_level = criteria_result.get("criteria_level", "")
                cr_id = criteria_level_to_id.get(cr_level, 0)
                if cr_id == 0 and "." in cr_level:
                    cr_id = criteria_level_to_id.get(cr_level.split(".")[-1], 0)
                db_result = GradingResult(
                    submission_id=submission.id,
                    criteria_id=cr_id or (criteria[0].id if criteria else 0),
                    achieved=criteria_result.get("achieved", False),
                    score=criteria_result.get("score", 0),
                    max_score=100,
                    missing_points=json.dumps(missing_pts, ensure_ascii=False),
                    feedback=teacher_facing_feedback(
                        criteria_result.get("feedback", "")
                    ),
                    next_level_requirements=json.dumps(
                        criteria_result.get("next_level_requirements", []),
                        ensure_ascii=False,
                    ),
                )
                db.add(db_result)

            grade_level_db = str(result.get("grade_level") or "")
            inst_disp = result.get("institutional_grade_display") or (
                (result.get("institutional_resolution") or {}).get("display_grade_ar")
            )
            result["btec_grade_level"] = grade_level_db
            if inst_disp:
                result["institutional_grade_display"] = inst_disp

            summary = GradingSummary(
                submission_id=submission.id,
                total_score=result["total_score"],
                max_score=result["max_score"],
                percentage=result["percentage"],
                overall_feedback=result.get("overall_feedback", ""),
                strengths=json.dumps(result.get("strengths", []), ensure_ascii=False),
                improvements=json.dumps(
                    result.get("improvements", []), ensure_ascii=False
                ),
                grade_level=grade_level_db,
                ai_likelihood=result.get("ai_likelihood", 0),
            )
            db.add(summary)
            db.flush()
            result["submission_id"] = submission.id
            try:
                from app.criteria_result_finalizer import sync_criteria_results_to_db

                sync_criteria_results_to_db(db, submission.id, result)
            except Exception as _sync_err:
                print(f"⚠️ [CRITERIA-DB-SYNC] skipped: {_sync_err}")
            db.commit()

        for cached in cached_results:
            source_id = cached.get("submission_id")
            if not source_id:
                continue
            source_sub = db.query(Submission).filter(Submission.id == source_id).first()
            if not source_sub:
                continue
            _clone_graded_submission(
                db,
                source_sub,
                batch_id=batch.id,
                assignment_id=assignment_id,
                user_id=user_id,
            )
            print(
                f"✅ [CACHE-CLONE] {source_sub.student_name} → batch {batch.id} "
                f"(from submission #{source_id})"
            )

        was_cancelled = bool(prog.get("cancelled"))
        total_processed = len([r for r in results if r.get("success", False)]) + len(
            cached_results
        )
        batch.processed_students = total_processed  # type: ignore
        failed_students = [
            r for r in results if not r.get("success", False) and not r.get("cancelled")
        ]
        if was_cancelled:
            batch.status = BatchStatus.COMPLETED if total_processed > 0 else BatchStatus.FAILED  # type: ignore[assignment]
            cancel_msg = (
                f"أُوقف التصحيح يدوياً — اكتمل {total_processed} من {batch.total_students or len(student_files)} طالب"
                if total_processed > 0
                else "أُوقف التصحيح قبل إكمال أي طالب"
            )
            batch.failure_message = cancel_msg  # type: ignore[assignment]
        elif total_processed == 0:
            batch.status = BatchStatus.FAILED  # type: ignore[assignment]
            if failed_students:
                batch.failure_message = str(  # type: ignore[assignment]
                    failed_students[0].get("error") or "فشل تصحيح جميع الطلاب"
                )
            else:
                batch.failure_message = "لم يُصحَّح أي طالب — تحقق من ملف التسليم."  # type: ignore[assignment]
        else:
            batch.status = BatchStatus.COMPLETED  # type: ignore[assignment]
            if failed_students:
                batch.failure_message = f"اكتمل جزئياً: {len(failed_students)} من {len(results)} فشل"  # type: ignore[assignment]
            else:
                batch.failure_message = None  # type: ignore[assignment]
        db.commit()

        # Release the UI as soon as grades are persisted — PDF / plagiarism / trajectory
        # can take minutes and must not block redirect to batch-results.
        if total_processed > 0 and not was_cancelled:
            prog.update(
                {
                    "finished": True,
                    "failed": False,
                    "batch_id": batch.id,
                    "completed": max(int(prog.get("total") or 0), total_processed),
                    "percent": 100,
                    "current_phase": "",
                    "current_student": "",
                    "student_progress": 0.0,
                    "final_response": {
                        "success": True,
                        "batch_id": batch.id,
                        "total_students": batch.total_students,
                        "processed": total_processed,
                    },
                }
            )
            _commit_progress(batch_progress, assignment_id, prog)

        try:
            batch_submissions = (
                db.query(Submission)
                .filter(
                    Submission.batch_id == batch.id,
                    Submission.status == SubmissionStatus.COMPLETED,  # type: ignore
                )
                .all()
            )
            if len(batch_submissions) > 1:
                for bsub in batch_submissions:
                    check_plagiarism_for_submission(bsub.id, db)  # type: ignore
        except Exception as plag_exc:
            print(f" [PLAGIARISM ERROR] {plag_exc}")

        for result in results:
            if not result.get("success") or "submission_id" not in result:
                continue
            sub_id = result["submission_id"]
            plag_summary = (
                db.query(GradingSummary)
                .filter(GradingSummary.submission_id == sub_id)
                .first()
            )
            if plag_summary and plag_summary.plagiarism_max_similarity > 0:  # type: ignore
                top_matches = (
                    db.query(models.PlagiarismCheck)
                    .filter(models.PlagiarismCheck.submission_id == sub_id)
                    .order_by(models.PlagiarismCheck.similarity_percentage.desc())
                    .limit(5)
                    .all()
                )
                matches_data = []
                for match in top_matches:
                    compared_sub = db.query(Submission).get(match.compared_submission_id)
                    matches_data.append(
                        {
                            "student": (
                                compared_sub.student_name if compared_sub else "Unknown"
                            ),
                            "percentage": match.similarity_percentage,
                            "is_suspicious": match.is_suspicious,
                        }
                    )
                result["plagiarism_info"] = {
                    "max_similarity": plag_summary.plagiarism_max_similarity,
                    "suspicious_count": plag_summary.plagiarism_suspicious_count,
                    "matches": matches_data,
                }

            try:
                from app.btec_criteria_governance import ensure_clean_grading_result_feedback

                ensure_clean_grading_result_feedback(result)
            except Exception:
                pass

            _snap = {k: v for k, v in result.items() if k != "student_text"}
            _grading_hash = result.get("grading_hash") or hash_submission_file(
                str(result.get("file_path") or ""), ""
            )
            _snap = attach_governance_to_payload(
                _snap,
                grading_hash=_grading_hash,
                grade_level=str(result.get("grade_level") or ""),
                percentage=float(result.get("percentage") or 0),
            )
            _snap = compact_snapshot_for_storage(
                _snap,
                prog.get("grading_mode") or policy.get("grading_mode") or grading_mode,
            )
            _sub_for_snap = db.query(Submission).filter(Submission.id == sub_id).first()
            if _sub_for_snap:
                _snap_blob = json.dumps(_snap, ensure_ascii=False)
                _sub_for_snap.grading_snapshot_json = _snap_blob  # type: ignore

            report_path = REPORTS_DIR / f"report_{sub_id}.pdf"
            try:
                generate_student_report_pdf(
                    result["student_name"],
                    result.get("student_email", ""),
                    result,
                    str(report_path),
                )
                report = StudentReport(
                    submission_id=sub_id,
                    report_file_url=f"/uploads/reports/report_{sub_id}.pdf",
                    report_file_path=str(report_path),  # type: ignore
                )
                db.add(report)
            except Exception as pdf_exc:
                print(
                    f"⚠️ [PDF] report skipped for {result.get('student_name', sub_id)}: {pdf_exc}"
                )
                result["pdf_error"] = str(pdf_exc)

        db.commit()

        if skip_grading_cache:
            print(
                "🔄 [FORCE REGRADE] Skipping canonical drift supersession — "
                "keeping fresh AI grades"
            )
        else:
            try:
                drift_incidents = reconcile_canonical_drift_for_assignment(db, assignment_id)
                if drift_incidents:
                    print(
                        f"🏛️ [GFM_CANONICAL_DRIFT] {len(drift_incidents)} incident(s) "
                        f"reconciled for assignment {assignment_id}"
                    )
            except Exception as drift_exc:
                print(f" [GOVERNANCE DRIFT ERROR] {drift_exc}")

        try:
            from app.canonical_stability_trajectory import build_governance_trajectory_report

            build_governance_trajectory_report(
                db,
                assignment_id=assignment_id,
                batch_id=batch.id,
                record_snapshot=True,
            )
        except Exception as traj_exc:
            print(f" [STABILITY TRAJECTORY ERROR] {traj_exc}")

        summary_report_path = REPORTS_DIR / f"batch_summary_{batch.id}.pdf"
        from app.models import Assignment

        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        report_title = (
            str(assignment.title).strip()
            if assignment and getattr(assignment, "title", None)
            else batch_name
        )
        generate_batch_summary_report(report_title, results, str(summary_report_path))

        if subject_bal_id is not None:
            subject_bal = (
                db.query(models.SubjectBalance)
                .filter(models.SubjectBalance.id == subject_bal_id)
                .first()
            )
            if subject_bal:
                subject_bal.assignments_used = (subject_bal.assignments_used or 0) + total_processed  # type: ignore
                db.commit()
        elif sub_id is not None:
            sub = db.query(models.Subscription).filter(models.Subscription.id == sub_id).first()
            if sub:
                sub.assignments_used = (sub.assignments_used or 0) + total_processed  # type: ignore
                db.commit()

        failed_students = [
            r for r in results if not r.get("success", False) and not r.get("cancelled")
        ]
        final_response: Dict[str, Any] = {
            "success": total_processed > 0,
            "batch_id": batch.id,
            "total_students": batch.total_students,
            "processed": batch.processed_students,
            "summary_report_url": f"/uploads/reports/batch_summary_{batch.id}.pdf",
            "upload_intake": batch_intake_manifest,
        }
        if was_cancelled:
            final_response["cancelled"] = True
            final_response["detail"] = batch.failure_message
        if failed_students:
            final_response["failed_count"] = len(failed_students)
            final_response["errors"] = [
                {
                    "student": r.get("student_name", "?"),
                    "error": r.get("error", "خطأ غير معروف"),
                }
                for r in failed_students
            ]
        if total_processed == 0 and not was_cancelled:
            _enrich_batch_failure_response(final_response)
        elif failed_students and not final_response.get("detail_ar"):
            _enrich_batch_failure_response(final_response)

        _sync_progress_percent(prog)
        failure_msg = (
            str(final_response.get("detail_ar") or final_response.get("detail") or "")
            if total_processed == 0
            else ""
        )
        prog.update(
            {
                "finished": True,
                "failed": total_processed == 0 and not was_cancelled,
                "cancelled": was_cancelled,
                "batch_id": batch.id,
                "final_response": final_response,
                "completed": prog.get("total", prog.get("completed", 0)),
                "student_progress": 0.0,
                "current_phase": "cancelled" if was_cancelled else "",
                "current_student": "",
                "percent": 100 if total_processed > 0 else (prog.get("percent") or 0),
                **(
                    {
                        "error": failure_msg,
                        "error_code": final_response.get("error_code"),
                    }
                    if total_processed == 0
                    else {}
                ),
            }
        )
        _commit_progress(batch_progress, assignment_id, prog)
        print(f"✅ [BATCH BG] Finished assignment {assignment_id} batch {batch_id}")

        async def delayed_pop():
            await asyncio.sleep(30)
            batch_progress.pop(assignment_id, None)

        asyncio.create_task(delayed_pop())

        from app.batch_checkpoint import delete_batch_checkpoint

        delete_batch_checkpoint(batch_id)

    except Exception as exc:
        tb = traceback.format_exc()
        print(f"❌ [BATCH BG] {assignment_id}: {exc}\n{tb}")
        try:
            batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
            if batch:
                batch.status = BatchStatus.FAILED  # type: ignore
                batch.failure_message = str(exc) or type(exc).__name__  # type: ignore
                db.commit()
        except Exception:
            pass
        prog.update(
            {
                "finished": True,
                "failed": True,
                "error": str(exc) or type(exc).__name__,
                "final_response": {"success": False, "detail": str(exc)},
            }
        )
        _commit_progress(batch_progress, assignment_id, prog)
        from app.batch_checkpoint import delete_batch_checkpoint

        delete_batch_checkpoint(batch_id)
    finally:
        db.close()


_ORPHAN_FAILURE_MSG = (
    "توقّف التصحيح لأن الخادم أُعيد تشغيله دون حفظ نقطة استئناف. "
    "إن وُجدت ملفاتك على الخادم سيُستأنف التصحيح تلقائياً؛ وإلا أعد رفع الملفات."
)


_STUCK_IDLE_PHASES = frozenset({"", "starting", "preparing"})
_STUCK_IDLE_SECONDS = 20 * 60
_STUCK_ACTIVE_MAX_SECONDS = 3 * 3600
_STUCK_EXTRACT_SECONDS = 8 * 60


def _progress_is_stuck(info: dict) -> bool:
    """True when persisted/in-memory progress looks abandoned (common after restart)."""
    if not info or info.get("finished") or info.get("failed"):
        return False
    phase = str(info.get("current_phase") or "")
    started = float(info.get("start_time") or 0)
    if not started:
        return True
    elapsed = time.time() - started
    sp = float(info.get("student_progress") or 0)
    completed = int(info.get("completed") or 0)
    total = int(info.get("total") or 0)
    if total > 0 and completed >= total and phase in ("saving", ""):
        return elapsed > 120
    if phase == "extracting" and sp < 0.30:
        return elapsed > _STUCK_EXTRACT_SECONDS
    if phase in _STUCK_IDLE_PHASES:
        return elapsed > _STUCK_IDLE_SECONDS
    if phase in ("grading", "extracting", "extracting_archive", "vision", "runtime", "inventory", "saving"):
        return elapsed > _STUCK_ACTIVE_MAX_SECONDS
    return elapsed > _STUCK_IDLE_SECONDS


def ensure_assignment_progress_loaded(
    batch_progress: dict,
    assignment_id: int,
) -> Optional[Dict[str, Any]]:
    """Merge persisted progress into memory before lock decisions."""
    info = batch_progress.get(assignment_id)
    if info is not None:
        return info
    from app.batch_progress_store import load_assignment_progress

    data = load_assignment_progress(assignment_id)
    if data:
        batch_progress[assignment_id] = data
        return data
    return None


def release_assignment_batch_lock(batch_progress: dict, assignment_id: int) -> None:
    """Clear assignment-wide lock so a new grading run can start."""
    from app.batch_progress_store import clear_assignment_progress

    batch_progress.pop(assignment_id, None)
    clear_assignment_progress(assignment_id)


def pro_clear_assignment_lock_for_new_upload(
    batch_progress: dict,
    assignment_id: int,
    db,
    *,
    reason: str = "pro_single_upload",
) -> bool:
    """
    PRO (deep) single-student only: drop stale assignment locks so a new upload can start.
    Does not alter BASIC (fast) multi-student locks.
    """
    from app.grading_mode_policy import normalize_grading_mode_choice
    from app.models import BatchGrading, BatchStatus

    info = ensure_assignment_progress_loaded(batch_progress, assignment_id)
    if info:
        mode = normalize_grading_mode_choice(str(info.get("grading_mode") or "deep"))
        if mode != "deep":
            return False
        if int(info.get("total") or 0) > 1:
            return False
        if not info.get("finished"):
            request_batch_cancel(batch_progress, assignment_id)

    _bump_assignment_job_generation(assignment_id)
    release_assignment_batch_lock(batch_progress, assignment_id)

    try:
        from app.batch_checkpoint import pause_pro_single_student_checkpoints_for_assignment

        paused = pause_pro_single_student_checkpoints_for_assignment(assignment_id)
        if paused:
            print(
                f"⏸️ [PRO-LOCK] paused {paused} checkpoint(s) for assignment={assignment_id} ({reason})"
            )
    except Exception as exc:
        print(f"⚠️ [PRO-LOCK] checkpoint pause failed assignment={assignment_id}: {exc}")

    try:
        active_batches = (
            db.query(BatchGrading)
            .filter(
                BatchGrading.assignment_id == assignment_id,
                BatchGrading.status.in_([BatchStatus.PROCESSING, BatchStatus.PENDING]),
            )
            .all()
        )
        for batch in active_batches:
            if int(batch.total_students or 0) > 1:
                continue
            batch.status = BatchStatus.FAILED  # type: ignore[assignment]
            batch.failure_message = (  # type: ignore[assignment]
                "أُلغي لبدء تصحيح PRO جديد لنفس الطالب. أعد الرفع إن لزم."
            )
        if active_batches:
            db.commit()
    except Exception as exc:
        db.rollback()
        print(f"⚠️ [PRO-LOCK] DB batch finalize failed assignment={assignment_id}: {exc}")

    print(f"🔁 [PRO-LOCK] cleared assignment lock assignment={assignment_id} ({reason})")
    return True


def should_supersede_assignment_lock(
    info: dict | None,
    *,
    single_student_archive: bool,
    force_regrade: bool,
) -> bool:
    """Allow a new single-student run to replace a stuck or duplicate in-flight job."""
    if force_regrade:
        return True
    if not info or info.get("finished"):
        return False
    if _progress_is_stuck(info):
        return True
    # Same pipeline as «batch» but often total=1 (PRO / أرشيف طالب واحد).
    if int(info.get("total") or 0) <= 1:
        return True
    return False


def clear_stale_batch_lock(
    batch_progress: dict,
    assignment_id: int,
    db,
) -> None:
    """Drop in-memory batch lock when the DB batch is no longer active."""
    info = batch_progress.get(assignment_id)
    if not info:
        return
    if info.get("finished"):
        release_assignment_batch_lock(batch_progress, assignment_id)
        return
    if _progress_is_stuck(info):
        print(
            f"🔓 [BATCH-LOCK] clearing stuck progress for assignment={assignment_id} "
            f"(phase={info.get('current_phase')!r}, batch={info.get('batch_id')})"
        )
        release_assignment_batch_lock(batch_progress, assignment_id)
        return

    batch_id = info.get("batch_id")
    if batch_id:
        batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
        if batch:
            status = (
                batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status)
            )
            if status in (BatchStatus.FAILED.value, BatchStatus.COMPLETED.value):
                info["finished"] = True
                release_assignment_batch_lock(batch_progress, assignment_id)
                return

    latest = (
        db.query(BatchGrading)
        .filter(BatchGrading.assignment_id == assignment_id)
        .order_by(BatchGrading.id.desc())
        .first()
    )
    if latest:
        latest_status = (
            latest.status.value
            if hasattr(latest.status, "value")
            else str(latest.status)
        )
        if latest_status in (BatchStatus.FAILED.value, BatchStatus.COMPLETED.value):
            release_assignment_batch_lock(batch_progress, assignment_id)
            return
        if batch_id and latest.id != batch_id:
            release_assignment_batch_lock(batch_progress, assignment_id)
            return


def assignment_batch_is_locked(
    batch_progress: dict,
    assignment_id: int,
    db,
) -> bool:
    ensure_assignment_progress_loaded(batch_progress, assignment_id)
    clear_stale_batch_lock(batch_progress, assignment_id, db)
    info = batch_progress.get(assignment_id)
    return bool(info and not info.get("finished"))


def finalize_stale_processing_batch(batch: BatchGrading, *, message: str | None = None) -> None:
    """Mark a DB batch as failed when in-memory progress was lost."""
    batch.status = BatchStatus.FAILED  # type: ignore[assignment]
    batch.failure_message = message or _ORPHAN_FAILURE_MSG  # type: ignore[assignment]


def recover_orphaned_batches_on_startup() -> int:
    """Fail only batches with no checkpoint and no extracted files after restart."""
    from app.batch_checkpoint import (
        batch_ids_with_checkpoints,
        batch_is_resumable_after_restart,
    )

    skip_ids = batch_ids_with_checkpoints()
    db = SessionLocal()
    try:
        orphans = (
            db.query(BatchGrading)
            .filter(BatchGrading.status.in_([BatchStatus.PROCESSING, BatchStatus.PENDING]))
            .all()
        )
        if not orphans:
            return 0
        marked = 0
        for batch in orphans:
            bid = int(batch.id)
            if bid in skip_ids or batch_is_resumable_after_restart(bid):
                continue
            finalize_stale_processing_batch(batch)
            marked += 1
        if not marked:
            return 0
        db.commit()
        print(f"⚠️ [BATCH-RECOVERY] marked {marked} orphaned batch(es) failed (no checkpoint/files)")
        return marked
    except Exception as exc:
        print(f"⚠️ [BATCH-RECOVERY] failed: {exc}")
        db.rollback()
        return 0
    finally:
        db.close()
