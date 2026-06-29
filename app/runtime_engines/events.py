"""Structured runtime events for replay, audit, and corroboration."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class RuntimeEvent:
    timestamp: float
    type: str
    severity: str = EventSeverity.INFO.value
    source: str = "runtime"
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        event_type: str,
        *,
        severity: str = EventSeverity.INFO.value,
        source: str = "runtime",
        **payload: Any,
    ) -> "RuntimeEvent":
        return cls(
            timestamp=time.time(),
            type=event_type,
            severity=severity,
            source=source,
            payload=payload,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeEventLog:
    """In-memory structured event log for a runtime session."""

    def __init__(self) -> None:
        self._events: List[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> RuntimeEvent:
        self._events.append(event)
        return event

    def record(
        self,
        event_type: str,
        *,
        severity: str = EventSeverity.INFO.value,
        source: str = "runtime",
        **payload: Any,
    ) -> RuntimeEvent:
        return self.emit(RuntimeEvent.now(event_type, severity=severity, source=source, **payload))

    @property
    def events(self) -> List[RuntimeEvent]:
        return list(self._events)

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            for event in self._events:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def filter_by_type(self, event_type: str) -> List[RuntimeEvent]:
        return [e for e in self._events if e.type == event_type]
