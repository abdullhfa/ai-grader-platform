"""Grade override engine — examiner decisions with audit trail."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.governance.audit_log import AuditEvent, append_audit_event
from app.governance.permissions import GovernanceRole, require_permission
from app.governance.review_session import ReviewSession, ReviewStatus, save_review_session


def apply_grade_override(
    session: ReviewSession,
    *,
    actor: str,
    actor_role: GovernanceRole,
    previous_grade: str,
    new_grade: str,
    reason: str,
    criterion_id: Optional[str] = None,
    replay_hash: Optional[str] = None,
) -> Dict[str, Any]:
    require_permission(actor_role, "override_grade")

    override_record = {
        "previous_grade": previous_grade,
        "new_grade": new_grade,
        "reason": reason,
        "criterion_id": criterion_id,
        "actor": actor,
        "actor_role": actor_role.value,
    }
    session.override_history.append(override_record)
    session.status = ReviewStatus.OVERRIDDEN
    session.examiner_id = actor
    save_review_session(session)

    audit = append_audit_event(
        AuditEvent(
            actor=actor,
            actor_role=actor_role.value,
            action="override_grade" if not criterion_id else "override_criterion",
            previous=previous_grade,
            new=new_grade,
            reason=reason,
            session_id=session.session_id,
            submission_key=session.submission_key,
            replay_hash=replay_hash or session.replay_hash,
            metadata={"criterion_id": criterion_id} if criterion_id else None,
        )
    )

    return {
        "status": "ok",
        "session": session.to_dict(),
        "override": override_record,
        "audit_event_id": audit.get("event_id"),
    }
