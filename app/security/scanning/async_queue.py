"""Async malware scan queue — decouple scan from runtime hot path."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


def async_malware_scan_enabled() -> bool:
    return os.environ.get("AI_GRADER_ASYNC_MALWARE_SCAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def enqueue_malware_scan(
    path: str,
    *,
    submission_key: str = "",
    student_name: str = "",
) -> Dict[str, Any]:
    """Queue malware scan on dedicated worker pool."""
    from app.tasks.celery_app import is_celery_enabled
    from app.tasks.worker_tasks import malware_scan_task

    if not is_celery_enabled():
        from app.security.scanning.pipeline import scan_submission_path

        return scan_submission_path(Path(path), submission_key=submission_key or student_name)

    job = malware_scan_task.delay(path, submission_key=submission_key or student_name)
    return {
        "status": "queued",
        "queue": "malware_jobs",
        "task_id": getattr(job, "id", None),
        "path": path,
    }


def wait_for_scan_result(task_id: str, *, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    from app.tasks.celery_app import celery_app

    try:
        result = celery_app.AsyncResult(task_id)
        payload = result.get(timeout=timeout)
        return payload if isinstance(payload, dict) else {"status": "unknown", "raw": payload}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
