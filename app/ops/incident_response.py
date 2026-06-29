"""Incident response workflow — security event → audit freeze → preservation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


class IncidentState(str, Enum):
    OPEN = "open"
    AUDIT_FROZEN = "audit_frozen"
    REPLAY_PRESERVED = "replay_preserved"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _incidents_dir() -> Path:
    return Path("uploads/ops/incidents")


def create_incident(
    *,
    event_type: str,
    severity: str,
    description: str,
    trace_id: Optional[str] = None,
    submission_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    incident_id = f"inc_{uuid4().hex[:12]}"
    record = {
        "incident_id": incident_id,
        "event_type": event_type,
        "severity": severity,
        "description": description,
        "state": IncidentState.OPEN.value,
        "trace_id": trace_id,
        "submission_key": submission_key,
        "session_id": session_id,
        "created_at": _utc_now(),
        "timeline": [{"state": IncidentState.OPEN.value, "at": _utc_now()}],
    }
    path = _incidents_dir() / f"{incident_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        from app.security.security_audit import log_security_action

        log_security_action(
            action="security_event",
            actor="system",
            resource=incident_id,
            outcome="open",
            trace_id=trace_id,
            metadata={"event_type": event_type, "severity": severity},
        )
    except Exception:
        pass

    return record


def advance_incident(incident_id: str, new_state: IncidentState, *, note: str = "") -> Dict[str, Any]:
    path = _incidents_dir() / f"{incident_id}.json"
    if not path.is_file():
        return {"ok": False, "error": "not_found"}
    record = json.loads(path.read_text(encoding="utf-8"))
    record["state"] = new_state.value
    record["timeline"].append({"state": new_state.value, "at": _utc_now(), "note": note})
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    if new_state == IncidentState.AUDIT_FROZEN:
        _write_freeze_marker(incident_id, record)
    if new_state == IncidentState.REPLAY_PRESERVED and record.get("submission_key") and record.get("session_id"):
        _preserve_replay(incident_id, record["submission_key"], record["session_id"])

    return {"ok": True, "incident": record}


def _write_freeze_marker(incident_id: str, record: Dict[str, Any]) -> None:
    marker = Path("uploads/ops/audit_freeze.json")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"active": True, "incident_id": incident_id, "since": _utc_now(), "record": record}, indent=2),
        encoding="utf-8",
    )


def _preserve_replay(incident_id: str, submission_key: str, session_id: str) -> None:
    import shutil

    src = Path("uploads/replay_snapshots") / submission_key / session_id
    if not src.is_dir():
        return
    dest = Path("uploads/ops/incident_preservation") / incident_id / submission_key / session_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copytree(src, dest)


def is_audit_frozen() -> bool:
    marker = Path("uploads/ops/audit_freeze.json")
    if not marker.is_file():
        return False
    try:
        return bool(json.loads(marker.read_text(encoding="utf-8")).get("active"))
    except (json.JSONDecodeError, OSError):
        return False


def run_incident_workflow(
    *,
    event_type: str,
    severity: str,
    description: str,
    trace_id: Optional[str] = None,
    submission_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Full workflow: event → audit freeze → replay preservation → investigating."""
    inc = create_incident(
        event_type=event_type,
        severity=severity,
        description=description,
        trace_id=trace_id,
        submission_key=submission_key,
        session_id=session_id,
    )
    iid = inc["incident_id"]
    advance_incident(iid, IncidentState.AUDIT_FROZEN, note="automatic_on_severity")
    if submission_key and session_id:
        advance_incident(iid, IncidentState.REPLAY_PRESERVED, note="replay_snapshot_copy")
    advance_incident(iid, IncidentState.INVESTIGATING, note="awaiting_resolution")
    path = _incidents_dir() / f"{iid}.json"
    return json.loads(path.read_text(encoding="utf-8"))
