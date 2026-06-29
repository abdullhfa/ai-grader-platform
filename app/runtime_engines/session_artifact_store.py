"""Session artifact store — durable layout for runtime evidence (Phase 2+)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SessionArtifactStore:
    """
    Canonical artifact layout per runtime session.

    uploads/runtime_sessions/{submission_key}/{session_id}/
        screenshots/
        traces/
        logs/
        fps/
        gameplay_video/
        runtime_events/
        manifest.json
    """

    session_root: Path

    @property
    def screenshots(self) -> Path:
        return self.session_root / "screenshots"

    @property
    def traces(self) -> Path:
        return self.session_root / "traces"

    @property
    def logs(self) -> Path:
        return self.session_root / "logs"

    @property
    def fps(self) -> Path:
        return self.session_root / "fps"

    @property
    def gameplay_video(self) -> Path:
        return self.session_root / "gameplay_video"

    @property
    def runtime_events(self) -> Path:
        return self.session_root / "runtime_events"

    @property
    def manifest_path(self) -> Path:
        return self.session_root / "manifest.json"

    def ensure(self) -> None:
        for directory in (
            self.screenshots,
            self.traces,
            self.logs,
            self.fps,
            self.gameplay_video,
            self.runtime_events,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_session(cls, submission_key: str, session_id: str) -> "SessionArtifactStore":
        root = Path("uploads/runtime_sessions") / submission_key / session_id
        store = cls(session_root=root)
        store.ensure()
        return store

    def write_manifest(self, payload: Dict[str, Any]) -> Path:
        self.ensure()
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.manifest_path

    def list_artifacts(self) -> Dict[str, List[str]]:
        def _list(folder: Path) -> List[str]:
            if not folder.is_dir():
                return []
            return sorted(str(p) for p in folder.rglob("*") if p.is_file())

        return {
            "screenshots": _list(self.screenshots),
            "traces": _list(self.traces),
            "logs": _list(self.logs),
            "fps": _list(self.fps),
            "gameplay_video": _list(self.gameplay_video),
            "runtime_events": _list(self.runtime_events),
        }
