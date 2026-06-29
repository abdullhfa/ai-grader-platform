"""Appeal decision record — uphold or modify based on replay review."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.appeals.appeal_audit import log_appeal_event
from app.appeals.appeal_case import AppealCase, AppealStatus, save_appeal_case
from app.governance.permissions import GovernanceRole, require_permission


def record_appeal_decision(
    case: AppealCase,
    *,
    actor: str,
    actor_role: GovernanceRole,
    decision: str,
    rationale: str,
    new_grade: Optional[str] = None,
) -> Dict[str, Any]:
    require_permission(actor_role, "resolve_appeal")

    decision_norm = decision.strip().lower()
    if decision_norm in ("uphold", "upheld", "accept"):
        case.status = AppealStatus.UPHELD
    elif decision_norm in ("partial", "partially_modified", "modify"):
        case.status = AppealStatus.PARTIALLY_MODIFIED
    else:
        case.status = AppealStatus.REJECTED_WITH_RATIONALE

    save_appeal_case(case)

    audit = log_appeal_event(
        case_id=case.case_id,
        actor=actor,
        action="appeal_decision",
        replay_hash=case.replay_hash,
        metadata={
            "decision": case.status.value,
            "rationale": rationale,
            "new_grade": new_grade,
            "actor_role": actor_role.value,
        },
    )

    return {
        "status": "resolved",
        "decision": case.status.value,
        "rationale": rationale,
        "new_grade": new_grade,
        "case": case.to_dict(),
        "audit_entry_id": audit.get("entry_id"),
    }
