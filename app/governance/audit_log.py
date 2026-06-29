"""Immutable governance audit log — append-only, replay-hash linked."""
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
class AuditEvent:
    actor: str
    action: str
    previous: Optional[str] = None
    new: Optional[str] = None
    reason: Optional[str] = None
    timestamp: str = field(default_factory=_utc_now)
    session_id: Optional[str] = None
    submission_key: Optional[str] = None
    replay_hash: Optional[str] = None
    actor_role: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload.get("metadata") is None:
            payload.pop("metadata", None)
        return payload


def _audit_root() -> Path:
    return Path("uploads/governance/audit")


def _session_log_path(session_id: str) -> Path:
    safe = session_id.replace("/", "_").replace("\\", "_")
    return _audit_root() / safe / "audit_log.jsonl"


def append_audit_event(event: AuditEvent) -> Dict[str, Any]:
    """Append immutable audit record — never overwrite."""
    path = _session_log_path(event.session_id or "global")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = event.to_dict()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    global_path = _audit_root() / "global_audit_log.jsonl"
    global_path.parent.mkdir(parents=True, exist_ok=True)
    with open(global_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return row


def read_audit_log(session_id: str, *, limit: int = 200) -> List[Dict[str, Any]]:
    path = _session_log_path(session_id)
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
