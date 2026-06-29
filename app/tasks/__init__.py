"""Distributed task queues — PHASE D."""
from app.tasks.celery_app import celery_app, is_celery_enabled

__all__ = ["celery_app", "is_celery_enabled"]
