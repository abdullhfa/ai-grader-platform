"""Institutional sign-off — signed evaluation hash linked to replay."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.ai_reasoning.snapshots.deterministic_hash import compute_snapshot_hash
from app.governance.audit_log import AuditEvent, append_audit_event
from app.governance.permissions import GovernanceRole, require_permission
from app.governance.review_session import ReviewSession, ReviewStatus, save_review_session


def compute_signed_evaluation_hash(
    *,
    replay_hash: str,
    examiner_id: str,
    timestamp: str,
    submission_key: str,
    session_id: str,
    final_grade: str,
) -> str:
    payload = {
        "replay_hash": replay_hash,
        "examiner_id": examiner_id,
        "timestamp": timestamp,
        "submission_key": submission_key,
        "session_id": session_id,
        "final_grade": final_grade,
        "schema": "signed_evaluation_v1",
    }
    return compute_snapshot_hash(payload)


def apply_signoff(
    session: ReviewSession,
    *,
    actor: str,
    actor_role: GovernanceRole,
    final_grade: str,
    replay_hash: str,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    require_permission(actor_role, "final_signoff")

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    signed_hash = compute_signed_evaluation_hash(
        replay_hash=replay_hash,
        examiner_id=actor,
        timestamp=ts,
        submission_key=session.submission_key,
        session_id=session.session_id,
        final_grade=final_grade,
    )

    session.status = ReviewStatus.SIGNED_OFF
    session.examiner_id = actor
    session.replay_hash = replay_hash
    save_review_session(session)

    signoff_doc = {
        "submission_key": session.submission_key,
        "session_id": session.session_id,
        "examiner_id": actor,
        "actor_role": actor_role.value,
        "final_grade": final_grade,
        "replay_hash": replay_hash,
        "signed_evaluation_hash": signed_hash,
        "timestamp": ts,
        "reason": reason,
    }

    out_dir = Path("uploads/governance/signoffs") / session.submission_key.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{session.session_id}.json"
    out_path.write_text(json.dumps(signoff_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    audit = append_audit_event(
        AuditEvent(
            actor=actor,
            actor_role=actor_role.value,
            action="institutional_signoff",
            previous=session.status.value if hasattr(session.status, "value") else str(session.status),
            new=final_grade,
            reason=reason or "institutional_signoff",
            session_id=session.session_id,
            submission_key=session.submission_key,
            replay_hash=replay_hash,
            metadata={"signed_evaluation_hash": signed_hash},
        )
    )

    return {
        "status": "signed_off",
        "signoff": signoff_doc,
        "audit_event_id": audit.get("event_id"),
    }
