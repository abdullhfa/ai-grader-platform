"""Examiner review session state — institutional workflow."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReviewStatus(str, Enum):
    PENDING = "pending_review"
    UNDER_REVIEW = "under_review"
    OVERRIDDEN = "overridden"
    ESCALATED = "escalated"
    SIGNED_OFF = "signed_off"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ReviewSession:
    submission_key: str
    session_id: str
    status: ReviewStatus = ReviewStatus.PENDING
    examiner_id: Optional[str] = None
    replay_hash: Optional[str] = None
    policy_actions: List[str] = field(default_factory=list)
    override_history: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def _session_path(submission_key: str, session_id: str) -> Path:
    safe_key = submission_key.replace("/", "_")
    return Path("uploads/governance/review_sessions") / safe_key / f"{session_id}.json"


def load_review_session(submission_key: str, session_id: str) -> Optional[ReviewSession]:
    path = _session_path(submission_key, session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = ReviewStatus(data.get("status", ReviewStatus.PENDING.value))
        return ReviewSession(**{k: v for k, v in data.items() if k in ReviewSession.__dataclass_fields__})
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def save_review_session(session: ReviewSession) -> Dict[str, Any]:
    session.updated_at = _utc_now()
    path = _session_path(session.submission_key, session.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return session.to_dict()


def get_or_create_review_session(
    submission_key: str,
    session_id: str,
    *,
    replay_hash: Optional[str] = None,
    policy_actions: Optional[List[str]] = None,
) -> ReviewSession:
    existing = load_review_session(submission_key, session_id)
    if existing:
        return existing
    session = ReviewSession(
        submission_key=submission_key,
        session_id=session_id,
        replay_hash=replay_hash,
        policy_actions=policy_actions or [],
    )
    save_review_session(session)
    return session
