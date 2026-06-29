"""Governance permissions — role-based access for examiner workflow."""
from __future__ import annotations

import os
from enum import Enum
from typing import FrozenSet, Optional, Set

from app.models import User, UserRole


class GovernanceRole(str, Enum):
    STUDENT = "student"
    EXAMINER = "examiner"
    SENIOR_EXAMINER = "senior_examiner"
    ADMIN = "admin"


PERMISSIONS: dict[GovernanceRole, FrozenSet[str]] = {
    GovernanceRole.STUDENT: frozenset({"view_feedback", "submit_appeal", "view_own_replay_summary"}),
    GovernanceRole.EXAMINER: frozenset({
        "view_feedback",
        "view_replay_bundle",
        "override_grade",
        "escalate_review",
        "view_audit_log",
    }),
    GovernanceRole.SENIOR_EXAMINER: frozenset({
        "view_feedback",
        "view_replay_bundle",
        "override_grade",
        "escalate_review",
        "view_audit_log",
        "final_signoff",
        "assign_appeal_reviewer",
        "resolve_appeal",
    }),
    GovernanceRole.ADMIN: frozenset({
        "view_feedback",
        "view_replay_bundle",
        "override_grade",
        "escalate_review",
        "view_audit_log",
        "final_signoff",
        "assign_appeal_reviewer",
        "resolve_appeal",
        "audit_export",
        "policy_admin",
    }),
}


def _examiner_emails() -> Set[str]:
    raw = os.environ.get("AI_GRADER_EXAMINER_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def resolve_governance_role(
    user: Optional[User],
    *,
    declared_role: Optional[str] = None,
    db: Optional[object] = None,
) -> GovernanceRole:
    """Resolve institutional role — DB RBAC first, then legacy fallbacks."""
    if declared_role:
        try:
            return GovernanceRole(declared_role.strip().lower())
        except ValueError:
            pass

    if user is not None and db is not None:
        try:
            from app.auth.permissions_store import get_primary_governance_role, seed_rbac_defaults

            seed_rbac_defaults(db)
            stored = get_primary_governance_role(db, int(user.id))
            if stored:
                return GovernanceRole(stored)
        except Exception:
            pass

    if user is None:
        dev = os.environ.get("AI_GRADER_GOVERNANCE_DEV_ROLE", "").strip().lower()
        if dev:
            try:
                return GovernanceRole(dev)
            except ValueError:
                pass
        return GovernanceRole.STUDENT

    if user.role == UserRole.ADMIN:
        return GovernanceRole.ADMIN

    email = (user.email or "").lower()
    if email in _examiner_emails():
        return GovernanceRole.EXAMINER

    title = (getattr(user, "job_title", None) or "").lower()
    if "senior" in title and "examiner" in title:
        return GovernanceRole.SENIOR_EXAMINER
    if "examiner" in title or "moderator" in title or "teacher" in title:
        return GovernanceRole.EXAMINER

    return GovernanceRole.STUDENT


def has_permission(role: GovernanceRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())


def require_permission(role: GovernanceRole, permission: str) -> None:
    if not has_permission(role, permission):
        raise PermissionError(f"role={role.value} lacks permission={permission}")
