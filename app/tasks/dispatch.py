"""Task dispatch — Celery when enabled, synchronous fallback otherwise."""
from __future__ import annotations

from typing import Any


def dispatch_or_run(task, *args, **kwargs) -> Any:
    """Use Celery when enabled; otherwise run synchronously."""
    from app.tasks.celery_app import is_celery_enabled

    if is_celery_enabled():
        return task.delay(*args, **kwargs)
    return task.apply(args=args, kwargs=kwargs).get()


def dispatch_async_only(task, *args, **kwargs) -> Any:
    """Enqueue without blocking; returns None when Celery disabled."""
    from app.tasks.celery_app import is_celery_enabled

    if is_celery_enabled():
        return task.delay(*args, **kwargs)
    return None
