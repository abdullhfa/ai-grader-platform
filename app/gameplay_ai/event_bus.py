"""Gameplay event bus — collects events from detectors into timeline."""
from __future__ import annotations

from typing import Any, Dict, List

from app.gameplay_ai.session_model import GameplayEvent, GameplayTimeline


class GameplayEventBus:
    def __init__(self) -> None:
        self._timeline = GameplayTimeline()

    @property
    def timeline(self) -> GameplayTimeline:
        return self._timeline

    def emit(
        self,
        event_type: str,
        *,
        timestamp: float = 0.0,
        confidence: float = 0.5,
        severity: str = "info",
        source: str = "gameplay_ai",
        **payload: Any,
    ) -> GameplayEvent:
        event = GameplayEvent(
            timestamp=timestamp,
            type=event_type,
            severity=severity,
            source=source,
            confidence=confidence,
            payload=payload,
        )
        self._timeline.add(event)
        return event

    def extend_runtime_events(self, runtime_events: List[Dict[str, Any]]) -> None:
        for raw in runtime_events or []:
            if not isinstance(raw, dict):
                continue
            self.emit(
                str(raw.get("type") or "runtime_event"),
                timestamp=float(raw.get("timestamp") or 0.0),
                confidence=0.9,
                source=str(raw.get("source") or "runtime"),
                severity=str(raw.get("severity") or "info"),
                **(raw.get("payload") or {}),
            )

    def to_dict(self) -> Dict[str, Any]:
        return self._timeline.to_dict()
