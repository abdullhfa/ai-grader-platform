"""Gameplay video capture helpers — wraps runtime recordings."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.gameplay_ai.frame_extractor import build_frame_sequence
from app.gameplay_ai.session_model import GameplayRecordingSession


def load_recording_session(
    submission_key: str,
    session_id: str,
    *,
    telemetry: Optional[Dict[str, Any]] = None,
    runtime_events: Optional[list] = None,
) -> GameplayRecordingSession:
    artifact_root = Path("uploads/runtime_sessions") / submission_key / session_id
    video_candidates = [
        artifact_root / "gameplay_video" / "session_capture.mp4",
        artifact_root / "gameplay_video" / "capture.mp4",
    ]
    video_path = next((p for p in video_candidates if p.is_file()), None)

    frames, timestamps, _meta = build_frame_sequence(artifact_root, video_path=video_path)
    return GameplayRecordingSession(
        session_id=session_id,
        submission_key=submission_key,
        artifact_root=artifact_root,
        video_path=video_path,
        frame_paths=frames,
        frame_timestamps=timestamps,
        telemetry=telemetry or {},
        runtime_events=list(runtime_events or []),
    )


def session_from_manifest(manifest: Dict[str, Any]) -> Optional[GameplayRecordingSession]:
    session_id = manifest.get("session_id")
    submission_key = manifest.get("submission_key")
    if not session_id or not submission_key:
        return None
    artifact_root = Path("uploads/runtime_sessions") / str(submission_key) / str(session_id)
    if not artifact_root.is_dir():
        return None
    return load_recording_session(
        str(submission_key),
        str(session_id),
        telemetry=manifest.get("telemetry") or {},
        runtime_events=manifest.get("events") or [],
    )
