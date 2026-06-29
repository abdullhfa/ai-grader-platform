"""Session manager — trace correlation for institutional audit."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _trace_index_path() -> Path:
    return Path("uploads/ops/session_traces.json")


def attach_trace_to_session(session_id: str, trace_id: str) -> None:
    path = _trace_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, str] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[session_id] = trace_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_trace_for_session(session_id: str) -> Optional[str]:
    path = _trace_index_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(session_id)
    except (json.JSONDecodeError, OSError):
        return None
