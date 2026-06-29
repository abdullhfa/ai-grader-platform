"""Queue names — isolated worker pools."""
from __future__ import annotations

QUEUE_AI = "ai_grading"
QUEUE_RUNTIME = "runtime_jobs"
QUEUE_REPLAY = "replay_jobs"
QUEUE_OCR = "ocr_jobs"
QUEUE_CALIBRATION = "calibration_jobs"
QUEUE_DEAD_LETTER = "dead_letter"

QUEUE_UNITY_BUILD = "unity_build_jobs"

QUEUE_GAMEPLAY = "gameplay_jobs"
QUEUE_CV = "cv_jobs"
QUEUE_REASONING = "reasoning_jobs"
QUEUE_REPORT = "report_jobs"
QUEUE_MALWARE = "malware_jobs"

# Legacy alias — same worker pool as gameplay/CV
QUEUE_GAMEPLAY_LEGACY = "gameplay_analysis_jobs"

ALL_QUEUES = (
    QUEUE_AI,
    QUEUE_RUNTIME,
    QUEUE_REPLAY,
    QUEUE_OCR,
    QUEUE_CALIBRATION,
    QUEUE_UNITY_BUILD,
    QUEUE_GAMEPLAY,
    QUEUE_CV,
    QUEUE_REASONING,
    QUEUE_REPORT,
    QUEUE_MALWARE,
    QUEUE_GAMEPLAY_LEGACY,
    QUEUE_DEAD_LETTER,
)

TASK_ROUTES = {
    "app.tasks.worker_tasks.grade_batch_task": {"queue": QUEUE_AI},
    "app.tasks.worker_tasks.runtime_observation_task": {"queue": QUEUE_RUNTIME},
    "app.tasks.worker_tasks.replay_verify_task": {"queue": QUEUE_REPLAY},
    "app.tasks.worker_tasks.ocr_verify_task": {"queue": QUEUE_CV},
    "app.tasks.worker_tasks.calibration_task": {"queue": QUEUE_CALIBRATION},
    "app.tasks.worker_tasks.unity_build_task": {"queue": QUEUE_RUNTIME},
    "app.tasks.worker_tasks.gameplay_analysis_task": {"queue": QUEUE_GAMEPLAY},
    "app.tasks.worker_tasks.evidence_reasoning_task": {"queue": QUEUE_REASONING},
    "app.tasks.worker_tasks.report_generation_task": {"queue": QUEUE_REPORT},
    "app.tasks.worker_tasks.malware_scan_task": {"queue": QUEUE_MALWARE},
}
