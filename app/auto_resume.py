"""Automatic resume of PAUSED grading — no human "Complete" step.

``Cannot Run -> PAUSED -> dependency/evidence available -> automatic resume -> test -> grade``

Two levels, both driven by *re-checking the blocker*, never by a person:

* batch level — a checkpoint paused by the GameMaker toolchain preflight is
  re-checked by a background poller; once the preflight passes the exact saved
  checkpoint resumes (already extracted/completed students are not redone).
* result level — a grading result whose ``assessment_state`` is PAUSED/PROVISIONAL
  is resumed from its ``resume_from`` phase: only the runtime/inventory phase is
  re-run (AI-graded text and criteria are kept), then the terminal seal runs again.
  While a blocker remains, the result stays PAUSED and nothing is re-run.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("ai_grader.auto_resume")

_RESUMING: set[int] = set()

# blocker code -> () -> bool  (True = the blocker is gone)
def _unity_editor_present() -> bool:
    from app.runtime_engines.unity.build_runner import resolve_unity_binary

    return resolve_unity_binary() is not None


def _unity_build_enabled() -> bool:
    from app.runtime_engines.unity.engine import _auto_build_enabled

    return _auto_build_enabled()


def _godot_present() -> bool:
    from app.runtime_engines.godot.export_runner import resolve_godot_binary

    return resolve_godot_binary() is not None


def _node_present() -> bool:
    return bool(shutil.which("node") or shutil.which("nodejs"))


def _launcher_now() -> bool:
    # A previous failed probe is cached: re-probe so an install is noticed.
    from app.runtime_wine import reset_probe_cache

    reset_probe_cache()
    from app.runtime_engines.dependencies import can_launch_windows_exe

    return can_launch_windows_exe()


def _native_windows() -> bool:
    # A crash inside an emulator is only re-judged on a native Windows host.
    return sys.platform == "win32"


_CHECKS: Dict[str, Callable[[], bool]] = {
    "unity_editor_missing": _unity_editor_present,
    "unity_auto_build_disabled": _unity_build_enabled,
    "godot_binary_missing": _godot_present,
    "node_runtime_missing": _node_present,
    "windows_exe_launcher_unavailable": _launcher_now,
    "windows_emulator_run_fault": _native_windows,
    "runtime_gate_error": lambda: True,  # a plain retry is the remedy
    "unity_license_or_activation_fault": lambda: True,  # retry
}


def blocker_cleared(blocker: Dict[str, Any], *, submission_changed: bool = False) -> bool:
    code = str(blocker.get("code") or "")
    if blocker.get("kind") == "MISSING_ARTIFACT" or blocker.get("resolvable_by") == "upload":
        return submission_changed
    check = _CHECKS.get(code)
    if check is None:
        return False  # unknown blocker: never guess it away
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 - a broken check keeps the pause
        logger.exception("blocker check failed: %s", code)
        return False


def remaining_blockers(
    blockers: Sequence[Dict[str, Any]], *, submission_changed: bool = False
) -> List[Dict[str, Any]]:
    return [b for b in blockers if not blocker_cleared(b, submission_changed=submission_changed)]


from app.assessment_state import submission_signature  # noqa: E402


def _submission_changed(grading_result: Dict[str, Any], paths: Sequence[str]) -> bool:
    prior = (grading_result.get("assessment_state") or {}).get("submission_signature")
    return bool(prior) and prior != submission_signature(paths)


# ── result level ────────────────────────────────────────────────────────────
def resume_paused_grading_result(
    grading_result: Dict[str, Any],
    *,
    submission_paths: Optional[Sequence[str]] = None,
    build_inventory: Optional[Callable[..., Dict[str, Any]]] = None,
    finalize: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Resume ONE paused result from its checkpointed phase, or leave it paused."""
    state = grading_result.get("assessment_state") or {}
    if state.get("state") not in ("PAUSED", "PROVISIONAL"):
        return {"resumed": False, "reason": "not_paused", "state": state.get("state")}

    paths = list(submission_paths or grading_result.get("submission_paths") or [])
    changed = _submission_changed(grading_result, paths)
    left = remaining_blockers(state.get("blockers") or [], submission_changed=changed)
    if left:
        return {"resumed": False, "reason": "still_blocked", "blockers": left, "state": state["state"]}

    if build_inventory is None:
        from app.artifact_inventory import build_artifact_inventory as build_inventory
    if finalize is None:
        from app.criteria_result_finalizer import finalize_grading_criteria_results as finalize

    resume_from = state.get("resume_from") or "runtime"
    phases: List[str] = []
    old_inv = grading_result.get("artifact_inventory") or {}
    if resume_from in ("extracting", "runtime", "inventory"):
        # Only the runtime/inventory phase is re-run; AI-graded rows/text are kept.
        inv = build_inventory(
            submission_paths=paths,
            student_name=str(grading_result.get("student_name") or ""),
            grading_mode=str(grading_result.get("grading_mode") or "deep"),
        )
        grading_result["artifact_inventory"] = {**old_inv, **inv}
        phases.append("runtime")
    phases.append("finalizing")
    finalize(grading_result, artifact_inventory=grading_result.get("artifact_inventory"))
    new_state = grading_result.get("assessment_state") or {}
    new_state["submission_signature"] = submission_signature(paths)
    new_state["resumed_phases"] = phases
    new_state["resumed_at"] = time.time()
    grading_result["assessment_state"] = new_state
    return {"resumed": True, "phases": phases, "state": new_state.get("state")}


# ── batch level ─────────────────────────────────────────────────────────────
async def resume_paused_checkpoint(
    checkpoint: Dict[str, Any], batch_progress: dict
) -> Dict[str, Any]:
    """Re-check the pause; resume the exact checkpoint if the blocker is gone."""
    from app.batch_checkpoint import resume_batch_from_checkpoint, save_batch_checkpoint
    from app.batch_progress_store import load_assignment_progress, persist_assignment_progress
    from app.database import SessionLocal
    from app.models import BatchGrading, BatchStatus
    from app.runtime_engines.gamemaker.toolchain import preflight_gamemaker_runtime_dependency

    batch_id = int(checkpoint.get("batch_id") or 0)
    assignment_id = int(checkpoint.get("assignment_id") or 0)
    if not batch_id or batch_id in _RESUMING:
        return {"resumed": False, "reason": "busy_or_invalid"}
    _RESUMING.add(batch_id)
    try:
        preflight = await asyncio.to_thread(
            preflight_gamemaker_runtime_dependency,
            list(checkpoint.get("student_files") or []),
        )
        checkpoint["gamemaker_preflight"] = preflight
        if preflight.get("pause_required"):
            save_batch_checkpoint(batch_id, checkpoint)
            return {"resumed": False, "reason": "still_blocked", "preflight": preflight}

        for key in ("paused", "pause_kind", "pause_started_at"):
            checkpoint.pop(key, None)
        save_batch_checkpoint(batch_id, checkpoint)

        db = SessionLocal()
        try:
            batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
            if batch:
                batch.status = BatchStatus.PROCESSING  # type: ignore[assignment]
                batch.failure_message = None  # type: ignore[assignment]
                db.commit()
        finally:
            db.close()

        info = batch_progress.get(assignment_id) or load_assignment_progress(assignment_id) or {}
        for key in ("paused", "pause_kind", "required_dependency"):
            info.pop(key, None)
        info.update(
            {
                "batch_id": batch_id,
                "current_phase": "queued",
                "phase_label": "توفّر المتطلب — استُؤنف التصحيح تلقائياً من نقطة التوقف...",
                "resuming": True,
                "finished": False,
                "failed": False,
            }
        )
        batch_progress[assignment_id] = info
        persist_assignment_progress(assignment_id, info)
        resumed = await resume_batch_from_checkpoint(checkpoint, batch_progress)
        return {"resumed": bool(resumed), "batch_id": batch_id}
    finally:
        _RESUMING.discard(batch_id)


def _paused_checkpoints() -> List[Dict[str, Any]]:
    from app.batch_checkpoint import _CHECKPOINT_DIR, load_batch_checkpoint

    found: List[Dict[str, Any]] = []
    if not _CHECKPOINT_DIR.is_dir():
        return found
    for path in _CHECKPOINT_DIR.glob("batch_*.json"):
        try:
            batch_id = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        ck = load_batch_checkpoint(batch_id)
        if ck and ck.get("paused"):
            found.append(ck)
    return found


async def auto_resume_paused_batches(batch_progress: dict) -> List[int]:
    """One sweep: resume every paused checkpoint whose blocker is gone."""
    resumed: List[int] = []
    for ck in _paused_checkpoints():
        outcome = await resume_paused_checkpoint(ck, batch_progress)
        if outcome.get("resumed"):
            resumed.append(int(ck["batch_id"]))
    return resumed


def auto_resume_interval_seconds() -> int:
    try:
        return max(5, int(os.environ.get("AI_GRADER_AUTO_RESUME_INTERVAL_SECONDS", "30")))
    except ValueError:
        return 30


async def run_auto_resume_loop(batch_progress: dict) -> None:
    """Background poller started at app startup (replaces the manual button)."""
    while True:
        try:
            await asyncio.sleep(auto_resume_interval_seconds())
            resumed = await auto_resume_paused_batches(batch_progress)
            if resumed:
                logger.info("auto-resumed batches: %s", resumed)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the loop must survive any sweep error
            logger.exception("auto-resume sweep failed")
