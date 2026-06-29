"""Unified security audit trail — login, export, replay, appeal access."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SecurityAuditEvent:
    action: str
    actor: str
    resource: str
    outcome: str = "allowed"
    trace_id: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=_utc_now)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload.get("metadata") is None:
            payload.pop("metadata", None)
        return payload


def _log_path() -> Path:
    return Path("uploads/security/security_audit.jsonl")


def log_security_event(event: SecurityAuditEvent) -> Dict[str, Any]:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = event.to_dict()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def log_security_action(
    *,
    action: str,
    actor: str,
    resource: str,
    outcome: str = "allowed",
    trace_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return log_security_event(
        SecurityAuditEvent(
            action=action,
            actor=actor,
            resource=resource,
            outcome=outcome,
            trace_id=trace_id,
            ip_address=ip_address,
            metadata=metadata,
        )
    )


def read_security_audit(*, limit: int = 200, action_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _log_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        try:
            row = json.loads(line)
            if action_prefix and not str(row.get("action", "")).startswith(action_prefix):
                continue
            rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows[-limit:]
