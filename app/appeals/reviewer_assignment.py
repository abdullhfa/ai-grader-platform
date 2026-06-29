"""Appeal reviewer assignment."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from app.appeals.appeal_case import AppealCase, AppealStatus, save_appeal_case
from app.appeals.appeal_audit import log_appeal_event


def _reviewer_pool() -> List[str]:
    raw = os.environ.get("AI_GRADER_APPEAL_REVIEWERS", "")
    pool = [e.strip() for e in raw.split(",") if e.strip()]
    return pool or ["senior_examiner@institution.local"]


def assign_reviewer(
    case: AppealCase,
    *,
    actor: str,
    reviewer: Optional[str] = None,
) -> Dict[str, object]:
    chosen = reviewer or _reviewer_pool()[0]
    case.assigned_reviewer = chosen
    case.status = AppealStatus.UNDER_HUMAN_REVIEW
    save_appeal_case(case)

    log_appeal_event(
        case_id=case.case_id,
        actor=actor,
        action="assign_reviewer",
        metadata={"reviewer": chosen},
        replay_hash=case.replay_hash,
    )

    return {"status": "assigned", "reviewer": chosen, "case": case.to_dict()}
