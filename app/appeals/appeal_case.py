"""Appeal case model — states and immutable records."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AppealStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_HUMAN_REVIEW = "under_human_review"
    REPLAY_AUDIT_REQUESTED = "replay_audit_requested"
    UPHELD = "upheld"
    PARTIALLY_MODIFIED = "partially_modified"
    REJECTED_WITH_RATIONALE = "rejected_with_rationale"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class AppealCase:
    case_id: str
    submission_key: str
    session_id: str
    student_id: str
    reason: str
    status: AppealStatus = AppealStatus.SUBMITTED
    replay_hash: Optional[str] = None
    assigned_reviewer: Optional[str] = None
    student_statement: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def _cases_root() -> Path:
    return Path("uploads/appeals/cases")


def _case_path(case_id: str) -> Path:
    return _cases_root() / f"{case_id}.json"


def new_case_id() -> str:
    return f"appeal_{uuid.uuid4().hex[:12]}"


def save_appeal_case(case: AppealCase) -> Dict[str, Any]:
    case.updated_at = _utc_now()
    _cases_root().mkdir(parents=True, exist_ok=True)
    _case_path(case.case_id).write_text(
        json.dumps(case.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return case.to_dict()


def load_appeal_case(case_id: str) -> Optional[AppealCase]:
    path = _case_path(case_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = AppealStatus(data.get("status", AppealStatus.SUBMITTED.value))
        return AppealCase(**{k: v for k, v in data.items() if k in AppealCase.__dataclass_fields__})
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def list_appeals_for_submission(submission_key: str) -> List[Dict[str, Any]]:
    root = _cases_root()
    if not root.is_dir():
        return []
    results = []
    for fp in root.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("submission_key") == submission_key:
                results.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(results, key=lambda r: r.get("created_at", ""), reverse=True)
