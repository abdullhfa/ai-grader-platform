"""Main gameplay intelligence pipeline — consumes runtime artifacts only."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.logging_setup import log_structured
from app.gameplay_ai.cv.freeze_detector import detect_freeze
from app.gameplay_ai.cv.hud_detector import detect_hud_regions
from app.gameplay_ai.cv.motion_detector import detect_motion
from app.gameplay_ai.cv.scene_change import detect_scene_changes
from app.gameplay_ai.cv.text_ocr import analyze_frames_ocr, combined_ocr_text
from app.gameplay_ai.cv.ui_detector import detect_ui_elements
from app.gameplay_ai.event_bus import GameplayEventBus
from app.gameplay_ai.evidence_linker import correlate_evidence
from app.gameplay_ai.gameplay.death_detector import detect_death
from app.gameplay_ai.gameplay.lose_detector import detect_lose
from app.gameplay_ai.gameplay.pause_detector import detect_pause
from app.gameplay_ai.gameplay.progression_detector import detect_progression
from app.gameplay_ai.gameplay.score_detector import detect_score_changes
from app.gameplay_ai.gameplay.win_detector import detect_win
from app.gameplay_ai.session_model import GameplayAnalysisResult, GameplayRecordingSession
from app.gameplay_ai.telemetry.frame_metrics import compute_frame_metrics
from app.gameplay_ai.telemetry.fps_monitor import analyze_fps, telemetry_to_events
from app.gameplay_ai.telemetry.input_trace import input_trace_to_events, load_input_trace
from app.gameplay_ai.video_capture import load_recording_session, session_from_manifest

logger = logging.getLogger("ai_grader.gameplay_ai")


def _gameplay_ai_enabled() -> bool:
    return os.environ.get("AI_GRADER_GAMEPLAY_AI", "1").lower() in ("1", "true", "yes", "on")


def run_gameplay_pipeline(session: GameplayRecordingSession) -> GameplayAnalysisResult:
    """
    Gameplay Intelligence Pipeline (Phase 3).

    Runtime → Artifacts → CV/Gameplay detectors → Timeline → Evidence links
    (No AI grading here — downstream only.)
    """
    bus = GameplayEventBus()
    bus.extend_runtime_events(session.runtime_events)
    bus.emit("pipeline_started", source="gameplay_ai", frame_count=len(session.frame_paths))

    paths = session.frame_paths
    timestamps = session.frame_timestamps or [float(i) for i in range(len(paths))]
    detections = []

    # --- CV layer (temporal) ---
    freeze_det = detect_freeze(paths)
    motion_det = detect_motion(paths)
    scene_det, scene_events = detect_scene_changes(paths, timestamps)
    hud_det = detect_hud_regions(paths)
    ocr_det = analyze_frames_ocr(paths)
    ui_det = detect_ui_elements(paths)

    for det in (freeze_det, motion_det, scene_det, hud_det, ocr_det, ui_det):
        detections.append(det)

    for event in scene_events:
        bus.timeline.add(event)

    ocr_text = combined_ocr_text(paths)

    # --- Gameplay layer ---
    win_det, win_events = detect_win(ocr_text)
    lose_det, lose_events = detect_lose(ocr_text)
    score_det, score_events = detect_score_changes(ocr_text)
    pause_det, pause_events = detect_pause(ocr_text)
    death_det, death_events = detect_death(ocr_text)
    prog_det, prog_events = detect_progression(scene_det.evidence, ocr_text)

    for det in (win_det, lose_det, score_det, pause_det, death_det, prog_det):
        detections.append(det)
    for event in win_events + lose_events + score_events + pause_events + death_events + prog_events:
        bus.timeline.add(event)

    # --- Telemetry layer ---
    fps_det = analyze_fps(session.telemetry)
    detections.append(fps_det)
    for event in telemetry_to_events(session.telemetry):
        bus.timeline.add(event)

    input_trace = load_input_trace(session.artifact_root)
    for event in input_trace_to_events(input_trace):
        bus.timeline.add(event)

    frame_metrics = compute_frame_metrics(paths, timestamps)
    if motion_det.label == "movement_detected":
        bus.emit("movement_detected", timestamp=timestamps[1] if len(timestamps) > 1 else 0.0, confidence=motion_det.confidence)
    if freeze_det.label == "freeze_detected":
        bus.emit("freeze_detected", timestamp=timestamps[-1] if timestamps else 0.0, confidence=freeze_det.confidence, severity="warning")

    evidence_links = correlate_evidence(detections)

    result = GameplayAnalysisResult(
        session=session,
        timeline=bus.timeline,
        detections=detections,
        cv_reports={
            "freeze": freeze_det.to_dict(),
            "motion": motion_det.to_dict(),
            "scene_change": scene_det.to_dict(),
            "hud": hud_det.to_dict(),
            "ocr": ocr_det.to_dict(),
            "ui": ui_det.to_dict(),
            "frame_metrics": frame_metrics,
        },
        gameplay_reports={
            "win": win_det.to_dict(),
            "lose": lose_det.to_dict(),
            "score": score_det.to_dict(),
            "pause": pause_det.to_dict(),
            "death": death_det.to_dict(),
            "progression": prog_det.to_dict(),
            "fps": fps_det.to_dict(),
            "input_trace": input_trace,
        },
        evidence_links=evidence_links,
    )

    _persist_analysis(session, result)
    bus.emit("pipeline_completed", source="gameplay_ai", detection_count=len(detections))
    log_structured(
        "gameplay_pipeline_complete",
        session_id=session.session_id,
        frame_count=len(paths),
        event_count=len(bus.timeline.events),
    )
    return result


def _persist_analysis(session: GameplayRecordingSession, result: GameplayAnalysisResult) -> Path:
    out_dir = session.artifact_root / "gameplay_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "analysis.json"
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    timeline_path = out_dir / "timeline.json"
    timeline_path.write_text(
        json.dumps(result.timeline.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def analyze_gameplay_artifacts(
    submission_key: str,
    session_id: str,
    *,
    telemetry: Optional[Dict[str, Any]] = None,
    runtime_events: Optional[list] = None,
) -> Dict[str, Any]:
    if not _gameplay_ai_enabled():
        return {"status": "disabled", "reason": "AI_GRADER_GAMEPLAY_AI=0"}

    session = load_recording_session(
        submission_key,
        session_id,
        telemetry=telemetry,
        runtime_events=runtime_events,
    )
    if not session.frame_paths and not session.video_path:
        return {"status": "skipped", "reason": "no_frames_or_video", "session_id": session_id}

    result = run_gameplay_pipeline(session)
    payload = result.to_dict()
    payload["status"] = "completed"
    return payload


def analyze_from_runtime_observation(observation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Hook: run gameplay AI after runtime orchestrator when session artifacts exist."""
    if not _gameplay_ai_enabled():
        return None

    session_id = observation.get("runtime_session_id")
    if not session_id:
        play_session = observation.get("unity_play_session") or {}
        session_id = (
            (play_session.get("observation") or {}).get("runtime_session_id")
            or session_id
        )

    platform = (observation.get("platform_analyses") or [{}])[0]
    signals = platform.get("signals") or {}
    submission_key = observation.get("submission_key") or observation.get("student_name") or "unknown"

    manifest_path = Path("uploads/runtime_sessions") / str(submission_key) / str(session_id) / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            submission_key = manifest.get("submission_key") or submission_key
            session_id = manifest.get("session_id") or session_id
        except (json.JSONDecodeError, OSError):
            pass

    if not session_id:
        return None

    artifact_root = Path("uploads/runtime_sessions") / str(submission_key) / str(session_id)
    if not artifact_root.is_dir():
        return None

    return analyze_gameplay_artifacts(
        str(submission_key),
        str(session_id),
        telemetry=observation.get("telemetry") or observation.get("runtime_metrics"),
        runtime_events=observation.get("runtime_events") or [],
    )
