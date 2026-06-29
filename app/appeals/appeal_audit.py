"""Immutable appeal audit trail."""
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
class AppealAuditEntry:
    case_id: str
    actor: str
    action: str
    timestamp: str = field(default_factory=_utc_now)
    replay_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload.get("metadata") is None:
            payload.pop("metadata", None)
        return payload


def _log_path(case_id: str) -> Path:
    return Path("uploads/appeals/audit") / case_id / "audit_log.jsonl"


def log_appeal_event(
    *,
    case_id: str,
    actor: str,
    action: str,
    replay_hash: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    entry = AppealAuditEntry(
        case_id=case_id,
        actor=actor,
        action=action,
        replay_hash=replay_hash,
        metadata=metadata,
    )
    path = _log_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = entry.to_dict()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_appeal_audit(case_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    path = _log_path(case_id)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
