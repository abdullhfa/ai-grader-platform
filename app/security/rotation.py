"""Secret rotation helpers — advisory metadata for ops."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def record_rotation_event(
    secret_key: str,
    *,
    actor: str = "system",
    note: Optional[str] = None,
) -> Dict[str, Any]:
    path = Path("uploads/security/rotation_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "secret_key": secret_key,
        "actor": actor,
        "timestamp": _utc_now(),
        "note": note or "rotation_recorded",
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def rotation_status() -> Dict[str, Any]:
    path = Path("uploads/security/rotation_log.jsonl")
    events: List[Dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").strip().splitlines()[-50:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"schema": "rotation_status_v1", "recent_events": events}
