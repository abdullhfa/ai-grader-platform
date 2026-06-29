"""Celery application — optional via AI_GRADER_CELERY_ENABLED."""
from __future__ import annotations

import os

from celery import Celery

from app.tasks.queues import ALL_QUEUES, TASK_ROUTES


def is_celery_enabled() -> bool:
    return os.environ.get("AI_GRADER_CELERY_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _broker_url() -> str:
    rabbit = os.environ.get("AI_GRADER_RABBITMQ_URL", "").strip()
    if rabbit:
        return rabbit
    return os.environ.get("AI_GRADER_REDIS_URL", "redis://127.0.0.1:6379/0")


def _result_backend() -> str:
    return os.environ.get("AI_GRADER_CELERY_RESULT_BACKEND", _broker_url())


celery_app = Celery("ai_grader", broker=_broker_url(), backend=_result_backend())

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes=TASK_ROUTES,
    task_queues={q: {} for q in ALL_QUEUES},
    task_default_queue="ai_grading",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={},
)

# Retry policy defaults
celery_app.conf.task_annotations = {
    "*": {
        "max_retries": int(os.environ.get("AI_GRADER_CELERY_MAX_RETRIES", "3")),
        "default_retry_delay": int(os.environ.get("AI_GRADER_CELERY_RETRY_DELAY", "30")),
    }
}

celery_app.autodiscover_tasks(["app.tasks"])
