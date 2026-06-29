"""Runtime engine base types — production foundation with telemetry and artifacts."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.events import RuntimeEventLog
from app.runtime_engines.session_artifact_store import SessionArtifactStore
from app.runtime_engines.telemetry import RuntimeTelemetry


class SessionStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    CRASHED = "crashed"
    TIMEOUT = "timeout"
    GATED = "gated"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class RuntimeMetrics:
    fps_samples: List[float] = field(default_factory=list)
    avg_fps: Optional[float] = None
    crash_detected: bool = False
    freeze_detected: bool = False
    soft_lock_detected: bool = False
    input_responsive: Optional[bool] = None
    frame_delta_score: float = 0.0


@dataclass
class RuntimeSession:
    session_id: str
    engine: str
    submission_key: str
    workspace: Path
    root: Path
    artifact_store: SessionArtifactStore
    status: SessionStatus = SessionStatus.PENDING
    screenshot_paths: List[Path] = field(default_factory=list)
    log_paths: List[Path] = field(default_factory=list)
    metrics: RuntimeMetrics = field(default_factory=RuntimeMetrics)
    telemetry: RuntimeTelemetry = field(default_factory=RuntimeTelemetry)
    events: RuntimeEventLog = field(default_factory=RuntimeEventLog)
    signals: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        engine: str,
        submission_key: str,
        root: Path,
        workspace: Optional[Path] = None,
        session_id: Optional[str] = None,
    ) -> "RuntimeSession":
        sid = session_id or str(uuid.uuid4())
        store = SessionArtifactStore.for_session(submission_key, sid)
        ws = workspace or store.session_root
        session = cls(
            session_id=sid,
            engine=engine,
            submission_key=submission_key,
            workspace=ws,
            root=root.resolve(),
            artifact_store=store,
        )
        session.events.record("session_created", engine=engine, root=str(root))
        return session


class RuntimeEngine(ABC):
    engine_id: str = "unknown"
    max_timeout_seconds: int = 120

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities()

    @classmethod
    @abstractmethod
    def detect(cls, root: Path) -> float:
        """Return confidence 0.0–1.0 that this engine owns the submission root."""

    @abstractmethod
    def prepare(self, session: RuntimeSession) -> None:
        """Prepare isolated workspace."""

    @abstractmethod
    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        """Launch and observe runtime — telemetry only, no AI grading."""

    def collect_evidence(self, session: RuntimeSession) -> Dict[str, Any]:
        """Normalize engine output for artifact store and downstream pipelines."""
        manifest = {
            "session_id": session.session_id,
            "engine": session.engine,
            "submission_key": session.submission_key,
            "status": session.status.value,
            "capabilities": self.capabilities().to_dict(),
            "signals": session.signals,
            "metrics": {
                "avg_fps": session.metrics.avg_fps or session.telemetry.avg_fps,
                "crash_detected": session.metrics.crash_detected,
                "freeze_detected": session.metrics.freeze_detected,
                "input_responsive": session.metrics.input_responsive,
                "frame_delta_score": session.metrics.frame_delta_score,
            },
            "telemetry": session.telemetry.to_dict(),
            "events": session.events.to_dicts(),
            "screenshots": [str(p) for p in session.screenshot_paths],
            "logs": [str(p) for p in session.log_paths],
            "errors": session.errors,
            "artifacts": session.artifact_store.list_artifacts(),
        }
        session.artifact_store.write_manifest(manifest)
        session.events.write_jsonl(session.artifact_store.runtime_events / "events.jsonl")
        return manifest

    def cleanup(self, session: RuntimeSession) -> None:
        """Best-effort teardown hook for subclasses."""
