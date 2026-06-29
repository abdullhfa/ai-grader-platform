"""Celery worker tasks — batch, runtime, replay, OCR, calibration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.tasks.celery_app import celery_app


def _write_dead_letter(task_name: str, payload: Dict[str, Any], error: str) -> None:
    row = {"task": task_name, "error": error, "payload": payload}
    line = json.dumps(row, ensure_ascii=False) + "\n"
    try:
        from app.storage.object_store import get_object_store

        store = get_object_store()
        key = f"audit/dead_letter/{task_name}.jsonl"
        existing = b""
        if store.exists(key):
            existing = store.get_bytes(key)
        store.put_bytes(key, existing + line.encode("utf-8"), content_type="application/x-ndjson")
    except Exception:
        path = Path("uploads/audit/dead_letter.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.grade_batch_task")
def grade_batch_task(self, assignment_id: int, student_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Async batch grading — same queue isolation as AI jobs."""
    import asyncio

    try:
        from app.core.grading_pipeline import run_batch_grading

        results = asyncio.run(run_batch_grading(student_files, {}, []))
        return {"status": "ok", "assignment_id": assignment_id, "count": len(results)}
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter("grade_batch_task", {"assignment_id": assignment_id}, str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.runtime_observation_task")
def runtime_observation_task(
    self,
    paths: List[str],
    submission_id: Optional[int] = None,
    student_name: str = "",
    batch_id: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        from app.infra.submission_guard import validate_submission_paths
        from app.observability.metrics import record_submission_rejected
        from app.runtime.sandbox_engine import run_sandbox_observation

        guard = validate_submission_paths([str(p) for p in paths])
        if not guard.get("ok"):
            for issue in guard.get("issues") or []:
                record_submission_rejected(str(issue).split(":", 1)[0])
            return {"status": "rejected", "guard": guard}

        from app.security.scanning.pipeline import scan_submission_path, scanning_enabled

        if scanning_enabled():
            from app.security.scanning.async_queue import async_malware_scan_enabled, enqueue_malware_scan

            for raw in paths:
                p = Path(str(raw))
                if not p.is_file():
                    continue
                if async_malware_scan_enabled():
                    queued = enqueue_malware_scan(
                        str(p),
                        submission_key=student_name or "",
                        student_name=student_name or "",
                    )
                    if queued.get("status") == "queued":
                        task_id = queued.get("task_id")
                        if task_id:
                            from app.security.scanning.async_queue import wait_for_scan_result

                            scan = wait_for_scan_result(task_id, timeout=45.0)
                        else:
                            scan = {"status": "error", "error": "no_task_id"}
                    else:
                        scan = queued
                else:
                    scan = scan_submission_path(p, submission_key=student_name or "")
                if scan and scan.get("status") == "rejected":
                    record_submission_rejected("malware_scan")
                    return {"status": "rejected", "malware_scan": scan}

        return run_sandbox_observation(
            paths,
            submission_id=submission_id,
            batch_id=batch_id,
            student_name=student_name,
            enable_smoke_test=True,
        )
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter(
                "runtime_observation_task",
                {"paths": paths, "submission_id": submission_id},
                str(exc),
            )
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.replay_verify_task")
def replay_verify_task(self, submission_id: int) -> Dict[str, Any]:
    try:
        from app.database import SessionLocal
        from app.models import Submission
        from app.academic_event_replay import build_academic_timeline_replay
        from app.deterministic_replay_engine import verify_deterministic_replay

        db = SessionLocal()
        try:
            sub = db.query(Submission).filter(Submission.id == submission_id).first()
            if not sub or not sub.grading_snapshot_json:
                return {"error": "not_found"}
            snap = json.loads(str(sub.grading_snapshot_json))
            tl = build_academic_timeline_replay(snap)
            return verify_deterministic_replay(tl.get("events") or [], snap)
        finally:
            db.close()
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter("replay_verify_task", {"submission_id": submission_id}, str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.ocr_verify_task")
def ocr_verify_task(self, image_paths: List[str]) -> Dict[str, Any]:
    try:
        from app.vision.verification_layer import analyze_runtime_screenshots

        obs = {
            "runtime_screenshots": [{"path": p, "visual_state": "unknown"} for p in image_paths]
        }
        return analyze_runtime_screenshots(obs)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter("ocr_verify_task", {"paths": image_paths}, str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.calibration_task")
def calibration_task(self, submission_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    try:
        from app.calibration.disagreement_report import build_disagreement_report
        from app.calibration.human_labels_io import export_system_snapshots_from_db

        root = Path(__file__).resolve().parents[2]
        labels = root / "app/calibration/human_labels_v1.json"
        systems = root / "app/calibration/reports/system_snapshots_latest.json"
        export_system_snapshots_from_db(submission_ids, systems)
        return build_disagreement_report(human_labels_path=labels, systems_path=systems)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter("calibration_task", {"submission_ids": submission_ids}, str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.unity_build_task")
def unity_build_task(
    self,
    project_path: str,
    student_name: str = "",
    output_name: str = "game.exe",
    run_playmode_tests: bool = False,
) -> Dict[str, Any]:
    try:
        from pathlib import Path

        from app.runtime_engines.unity.build_runner import (
            UnityBuildConfig,
            resolve_unity_binary,
            run_unity_build,
        )
        from app.runtime_engines.unity.playmode_runner import maybe_run_playmode_tests
        from app.runtime_engines.unity.project_probe import find_unity_project_root
        from app.runtime_observation_sandbox import observe_unity_windows_exe

        project_root = find_unity_project_root(Path(project_path))
        if not project_root:
            return {"status": "error", "error": "unity_project_not_found"}

        unity_bin = resolve_unity_binary()
        if not unity_bin:
            return {"status": "error", "error": "unity_binary_not_configured"}

        workspace = Path(f"uploads/runtime_sessions/{student_name or 'unity'}")
        workspace.mkdir(parents=True, exist_ok=True)
        build_result = run_unity_build(
            UnityBuildConfig(
                project_path=project_root,
                unity_path=unity_bin,
                output_exe=workspace / "build" / output_name,
                log_path=workspace / "unity_build.log",
            )
        )
        payload: Dict[str, Any] = {
            "status": "ok" if build_result.get("success") else "failed",
            "build": build_result,
            "project_root": str(project_root),
        }
        if run_playmode_tests:
            payload["playmode"] = maybe_run_playmode_tests(project_root, workspace)
        if build_result.get("artifact"):
            payload["smoke_test"] = observe_unity_windows_exe(Path(str(build_result["artifact"])))
        return payload
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter(
                "unity_build_task",
                {"project_path": project_path, "student_name": student_name},
                str(exc),
            )
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.gameplay_analysis_task")
def gameplay_analysis_task(self, submission_key: str, session_id: str) -> Dict[str, Any]:
    try:
        from app.gameplay_ai.pipeline import analyze_gameplay_artifacts
        from app.observability.metrics import record_gameplay_analysis

        result = analyze_gameplay_artifacts(submission_key, session_id)
        record_gameplay_analysis(result.get("status", "unknown"))
        return result
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter(
                "gameplay_analysis_task",
                {"submission_key": submission_key, "session_id": session_id},
                str(exc),
            )
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.evidence_reasoning_task")
def evidence_reasoning_task(
    self,
    submission_key: str,
    grading_result: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Async Phase 4 reasoning — does not block HTTP grading path."""
    try:
        from app.ai_reasoning.orchestrator import run_evidence_reasoning
        from app.observability.metrics import record_reasoning_outcome

        payload = run_evidence_reasoning(
            submission_key=submission_key,
            grading_result=grading_result,
            artifact_inventory=artifact_inventory,
            grading_criteria=grading_criteria,
        )
        final = payload.get("final_decision") or {}
        record_reasoning_outcome(
            payload.get("status", "unknown"),
            manual_review=bool(final.get("requires_manual_review")),
        )
        return payload
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter(
                "evidence_reasoning_task",
                {"submission_key": submission_key},
                str(exc),
            )
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.report_generation_task")
def report_generation_task(
    self,
    submission_key: str,
    grading_result: Dict[str, Any],
    report_format: str = "json",
) -> Dict[str, Any]:
    """PDF/JSON report generation — isolated report worker pool."""
    try:
        from app.storage.object_store import get_object_store

        store = get_object_store()
        key = f"reports/{submission_key}/grading_report.{report_format}"
        body = json.dumps(grading_result, ensure_ascii=False, indent=2).encode("utf-8")
        uri = store.put_bytes(key, body, content_type="application/json")
        return {"status": "ok", "uri": uri, "format": report_format}
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter(
                "report_generation_task",
                {"submission_key": submission_key},
                str(exc),
            )
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.worker_tasks.malware_scan_task")
def malware_scan_task(self, path: str, submission_key: str = "") -> Dict[str, Any]:
    """Async malware scan — isolated malware_jobs queue."""
    try:
        from app.security.scanning.pipeline import scan_submission_path

        return scan_submission_path(Path(path), submission_key=submission_key)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _write_dead_letter("malware_scan_task", {"path": path}, str(exc))
        raise self.retry(exc=exc)


def dispatch_or_run(task, *args, **kwargs):
    """Backward-compatible re-export."""
    from app.tasks.dispatch import dispatch_or_run as _dispatch

    return _dispatch(task, *args, **kwargs)
