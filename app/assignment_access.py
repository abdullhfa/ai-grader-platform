"""Assignment creation access control and DB cache lookup."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi.responses import JSONResponse  # type: ignore

# Mirrors create_assignment.html subjectUnitMap (subject → unit).
SUBJECT_UNIT_MAP: Dict[str, Dict[str, str]] = {
    "برمجة": {"level": "L3", "unit": "L3_1"},
    "شبكات": {"level": "L3", "unit": "L3_2"},
    "قواعد البيانات": {"level": "L3", "unit": "L3_3"},
    "تطوير الويب": {"level": "L3", "unit": "L3_4"},
    "مقدمة في تصميم الألعاب": {"level": "L2", "unit": "L2_9"},
    "الأمن السيبراني": {"level": "L3", "unit": "L3_5"},
    "الذكاء الاصطناعي": {"level": "L3", "unit": "L3_6"},
}

UNIT_SUBJECT_MAP: Dict[str, str] = {
    spec["unit"]: name for name, spec in SUBJECT_UNIT_MAP.items()
}


def _subjects_match(a: str, b: str) -> bool:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


def resolve_subject(subject: str | None, unit_number: str | None) -> str:
    """Resolve subscription subject from form field or BTEC unit key."""
    cleaned = (subject or "").strip()
    if cleaned:
        return cleaned
    unit_key = (unit_number or "").strip()
    if unit_key:
        return UNIT_SUBJECT_MAP.get(unit_key, "")
    return ""


def _parse_allowed_subjects(raw: str | None) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"[,|]", str(raw))
    return [p.strip() for p in parts if p.strip() and p.strip() != "أخرى"]


def _find_subject_balance(balances, subject: str):
    for bal in balances:
        if _subjects_match(str(bal.subject or ""), subject):
            return bal
    return None


def assignment_not_available_response() -> JSONResponse:
    """Returned when a non-admin requests a task that has not been created yet."""
    return JSONResponse(
        {
            "success": False,
            "assignment_not_available": True,
            "detail": (
                "المهمة غير متوفرة في النظام بعد. "
                "يرجى التأكد من ملف المهمة أو التواصل مع الإدارة لإنشائها."
            ),
        },
        status_code=404,
    )


def check_assignment_creation_access(
    db,
    user_id: int,
    *,
    subject: str | None,
    unit_number: str | None,
    is_admin: bool,
    for_request: bool = False,
) -> Tuple[Optional[JSONResponse], str]:
    """
    Return (error_response, resolved_subject).
    error_response is set when creation must be blocked.
    """
    from app.models import SubjectBalance  # type: ignore

    action = "طلب" if for_request else "إنشاء"

    if is_admin:
        return None, resolve_subject(subject, unit_number)

    resolved = resolve_subject(subject, unit_number)
    if unit_number and not resolved:
        return (
            JSONResponse(
                {
                    "success": False,
                    "subscription_required": True,
                    "detail": "تعذّر تحديد المادة لهذه الوحدة. يرجى اختيار مادة مشترك بها.",
                },
                status_code=403,
            ),
            "",
        )

    balances = (
        db.query(SubjectBalance)
        .filter(SubjectBalance.user_id == user_id)
        .all()
    )

    if balances:
        if not resolved:
            return (
                JSONResponse(
                    {
                        "success": False,
                        "subscription_required": True,
                        "detail": f"يجب اختيار مادة من اشتراكك ل{action} دليل المهمة.",
                    },
                    status_code=403,
                ),
                "",
            )
        subject_bal = _find_subject_balance(balances, resolved)
        if subject_bal is None:
            return (
                JSONResponse(
                    {
                        "success": False,
                        "subscription_required": True,
                        "detail": f"لم تشترك في مادة «{resolved}». لا يمكن {action} دليل لهذه الوحدة.",
                    },
                    status_code=403,
                ),
                "",
            )
        remaining = max(
            0,
            (subject_bal.assignments_limit or 0) - (subject_bal.assignments_used or 0),
        )
        if remaining <= 0:
            return (
                JSONResponse(
                    {
                        "success": False,
                        "subscription_required": True,
                        "detail": f"لقد استنفدت رصيدك لمادة {resolved}. يرجى تجديد الاشتراك.",
                    },
                    status_code=403,
                ),
                "",
            )
        return None, resolved

    # Global subscription fallback
    from app.models import Subscription, SubscriptionStatus  # type: ignore

    sub = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user_id,
            Subscription.status.in_(
                [SubscriptionStatus.ACTIVE, "active", "ACTIVE"]
            ),
        )
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if sub is None:
        return (
            JSONResponse(
                {
                    "success": False,
                    "subscription_required": True,
                    "detail": f"يجب الاشتراك أولاً ل{action} الواجبات",
                },
                status_code=403,
            ),
            "",
        )

    allowed = _parse_allowed_subjects(getattr(sub, "subjects", None))
    if allowed and resolved:
        if not any(_subjects_match(resolved, item) for item in allowed):
            return (
                JSONResponse(
                    {
                        "success": False,
                        "subscription_required": True,
                        "detail": f"اشتراكك لا يشمل مادة «{resolved}». يرجى الاشتراك في هذه المادة أولاً.",
                    },
                    status_code=403,
                ),
                "",
            )

    remaining = (sub.assignments_limit or 0) - (sub.assignments_used or 0)
    if remaining <= 0:
        return (
            JSONResponse(
                {
                    "success": False,
                    "subscription_required": True,
                    "detail": "لقد استنفدت عدد الواجبات المتاح. يرجى تجديد الاشتراك.",
                },
                status_code=403,
            ),
            "",
        )

    return None, resolved


def assignment_file_hash_from_url(assignment_file_url: str | None, assignments_dir: Path) -> str | None:
    if not assignment_file_url:
        return None
    fname = str(assignment_file_url).replace("\\", "/").split("/")[-1].strip()
    if not fname:
        return None
    fp = assignments_dir / fname
    if not fp.is_file():
        return None
    return hashlib.sha256(fp.read_bytes()).hexdigest()


def find_ready_assignment_in_db(
    db,
    *,
    user_id: int,
    content_hash: str,
    unit_number: str | None,
    assignment_raw: bytes,
    assignments_dir: Path,
):
    """
    Find an existing READY assignment without calling AI.
    Priority: same user + hash → any user + hash → same unit + same brief file.
    """
    from app.models import Assignment, AssignmentStatus  # type: ignore

    ready_filters = [
        Assignment.reference_solution_json.isnot(None),
        Assignment.status == AssignmentStatus.READY,
    ]

    existing_own = (
        db.query(Assignment)
        .filter(Assignment.content_hash == content_hash, Assignment.created_by == user_id, *ready_filters)
        .first()
    )
    if existing_own:
        return existing_own, "own_hash"

    cached_assignment = (
        db.query(Assignment)
        .filter(Assignment.content_hash == content_hash, *ready_filters)
        .first()
    )
    if cached_assignment:
        return cached_assignment, "global_hash"

    incoming_file_hash = hashlib.sha256(assignment_raw).hexdigest()
    unit_key = (unit_number or "").strip()
    if unit_key:
        unit_candidates = (
            db.query(Assignment)
            .filter(Assignment.unit_number == unit_key, *ready_filters)
            .order_by(Assignment.id.desc())
            .all()
        )
        for candidate in unit_candidates:
            stored_hash = assignment_file_hash_from_url(
                getattr(candidate, "assignment_file_url", None),
                assignments_dir,
            )
            if stored_hash and stored_hash == incoming_file_hash:
                return candidate, "unit_file_hash"

    return None, None


def find_ready_assignment_for_request(
    db,
    *,
    unit_number: str | None,
    assignment_raw: bytes,
    assignments_dir: Path,
):
    """
    Non-admin request flow: locate an admin-created READY assignment
    by BTEC unit + uploaded brief file hash (no AI, no new rows).
    """
    from app.models import Assignment, AssignmentStatus  # type: ignore

    ready_filters = [
        Assignment.reference_solution_json.isnot(None),
        Assignment.status == AssignmentStatus.READY,
    ]

    incoming_file_hash = hashlib.sha256(assignment_raw).hexdigest()
    unit_key = (unit_number or "").strip()
    if not unit_key:
        return None, None

    unit_candidates = (
        db.query(Assignment)
        .filter(Assignment.unit_number == unit_key, *ready_filters)
        .order_by(Assignment.id.desc())
        .all()
    )
    for candidate in unit_candidates:
        stored_hash = assignment_file_hash_from_url(
            getattr(candidate, "assignment_file_url", None),
            assignments_dir,
        )
        if stored_hash and stored_hash == incoming_file_hash:
            return candidate, "unit_file_hash"

    return None, None


def list_ready_assignments_for_unit(
    db,
    *,
    unit_number: str | None,
    admin_only: bool = True,
):
    """Return deduplicated READY assignments with guides for a BTEC unit."""
    from app.models import Assignment, AssignmentStatus, User, UserRole  # type: ignore

    unit_key = (unit_number or "").strip()
    if not unit_key:
        return []

    ready_filters = [
        Assignment.reference_solution_json.isnot(None),
        Assignment.status == AssignmentStatus.READY,
    ]
    query = db.query(Assignment).filter(Assignment.unit_number == unit_key, *ready_filters)
    if admin_only:
        query = query.join(User, Assignment.created_by == User.id).filter(
            User.role == UserRole.ADMIN
        )
    candidates = query.order_by(Assignment.id.desc()).all()

    seen: set[str] = set()
    unique: list = []
    for assignment in candidates:
        title_key = (assignment.title or "").strip().lower()
        hash_key = (getattr(assignment, "content_hash", None) or "").strip()
        dedupe_key = hash_key or f"title:{title_key}|unit:{unit_key}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(assignment)
    return unique


def assignment_request_item(assignment) -> Dict[str, Any]:
    """Serialize assignment for the user request picker."""
    created_at = getattr(assignment, "created_at", None)
    return {
        "id": assignment.id,
        "title": assignment.title,
        "description": (assignment.description or "").strip() or None,
        "unit_number": getattr(assignment, "unit_number", None),
        "unit_name": getattr(assignment, "unit_name", None),
        "subject": getattr(assignment, "subject", None),
        "created_at": created_at.isoformat() if created_at is not None else None,
    }
