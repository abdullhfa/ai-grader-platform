"""Examiner Mode — replay-first institutional review orchestrator."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.governance.audit_log import AuditEvent, append_audit_event
from app.governance.evidence_browser import browse_evidence
from app.governance.permissions import GovernanceRole, require_permission
from app.governance.policy_engine import evaluate_policies
from app.governance.replay_viewer import ReplayInspectionBundle, load_replay_inspection_bundle
from app.governance.review_session import (
    ReviewSession,
    ReviewStatus,
    get_or_create_review_session,
    load_review_session,
    save_review_session,
)


def parse_session_ref(session_ref: str) -> tuple[str, str]:
    """
    Parse ``{submission_key}/{session_id}`` or ``{submission_key}--{session_id}``.
    """
    if "--" in session_ref and "/" not in session_ref:
        parts = session_ref.split("--", 1)
        return parts[0], parts[1]
    if "/" in session_ref:
        parts = session_ref.split("/", 1)
        return parts[0], parts[1]
    raise ValueError("session_ref must be submission_key/session_id")


def load_examiner_review(
    session_ref: str,
    *,
    grading_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full examiner review payload — replay bundle + policy + evidence browser."""
    submission_key, session_id = parse_session_ref(session_ref)
    bundle = load_replay_inspection_bundle(submission_key, session_id)
    policy = evaluate_policies(bundle, grading_result)
    evidence = browse_evidence(bundle)

    review = get_or_create_review_session(
        submission_key,
        session_id,
        replay_hash=bundle.deterministic_hash,
        policy_actions=policy.get("required_actions") or [],
    )

    return {
        "review_session": review.to_dict(),
        "replay_bundle": bundle.to_dict(),
        "evidence_browser": evidence,
        "policy_evaluation": policy,
        "examiner_guidance": {
            "mode": "replay_first",
            "do_not_trust": "llm_summary_only",
            "inspect": [
                "deterministic_hash",
                "gameplay_timeline",
                "evidence_graph",
                "screenshots",
                "contradictions",
                "hallucination_flags",
            ],
        },
    }


def start_examiner_review(
    session_ref: str,
    *,
    actor: str,
    actor_role: GovernanceRole,
) -> Dict[str, Any]:
    require_permission(actor_role, "view_replay_bundle")
    submission_key, session_id = parse_session_ref(session_ref)
    payload = load_examiner_review(session_ref)

    session = load_review_session(submission_key, session_id)
    if session and session.status == ReviewStatus.PENDING:
        session.status = ReviewStatus.UNDER_REVIEW
        session.examiner_id = actor
        save_review_session(session)
        append_audit_event(
            AuditEvent(
                actor=actor,
                actor_role=actor_role.value,
                action="start_review",
                session_id=session_id,
                submission_key=submission_key,
                replay_hash=payload["replay_bundle"].get("deterministic_hash"),
            )
        )
        payload["review_session"] = session.to_dict()

    return payload


def escalate_review(
    session: ReviewSession,
    *,
    actor: str,
    actor_role: GovernanceRole,
    reason: str,
    target_role: str = "senior_examiner",
) -> Dict[str, Any]:
    require_permission(actor_role, "escalate_review")

    session.status = ReviewStatus.ESCALATED
    session.notes.append(f"escalated:{reason}")
    save_review_session(session)

    audit = append_audit_event(
        AuditEvent(
            actor=actor,
            actor_role=actor_role.value,
            action="escalate_review",
            reason=reason,
            session_id=session.session_id,
            submission_key=session.submission_key,
            replay_hash=session.replay_hash,
            metadata={"target_role": target_role},
        )
    )

    return {
        "status": "escalated",
        "session": session.to_dict(),
        "target_role": target_role,
        "audit_event_id": audit.get("event_id"),
    }
