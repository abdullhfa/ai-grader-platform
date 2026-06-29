"""Shared dependencies for API routers — no imports from main."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app import models


def orm_set(instance: object, name: str, value: object) -> None:
    setattr(instance, name, value)


def load_grading_snapshot(submission) -> Optional[Dict[str, Any]]:
    if not getattr(submission, "grading_snapshot_json", None):
        return None
    try:
        return json.loads(str(submission.grading_snapshot_json))
    except (json.JSONDecodeError, TypeError):
        return None


def get_templates(request: Request):
    return request.app.state.templates


def get_batch_progress_dict(request: Request) -> dict:
    return request.app.state.batch_progress


def app_title() -> str:
    return os.getenv("APP_TITLE", "أداة تصحيح واجبات الذكاء الاصطناعي")


def subscription_info_for_user(db: Session, user_id: int) -> dict:
    """Subscription details for templates/API (extracted from main)."""
    from app.services.subscription import get_subscription_info

    return get_subscription_info(db, user_id)
