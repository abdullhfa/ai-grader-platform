"""Identity audit — SSO login, role assignment events."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth.rbac_models import IdentityAuditLog


def log_identity_event(
    db: Session,
    *,
    action: str,
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    provider: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    row = IdentityAuditLog(
        user_id=user_id,
        email=email,
        action=action,
        provider=provider,
        trace_id=trace_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False)[:2000],
    )
    db.add(row)
    db.commit()
