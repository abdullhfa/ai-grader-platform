"""
PRO GameMaker Runtime Verification — build pipeline, object inspection, gameplay replay.

Pipeline:
  1. Extract .yyz → locate .yyp
  2. Optional IDE compile (AI_GRADER_GAMEMAKER_IDE)
  3. Object inspection (sprites/rooms/events/objects)
  4. Gameplay replay (EXE smoke or HTML5 headless) + screenshot comparison
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.gamemaker.build_runner import analyze_gamemaker_artifacts
from app.runtime_engines.gamemaker.object_inspection import inspect_gamemaker_objects
from app.runtime_engines.gamemaker.project_probe import GameMakerLayout, probe_gamemaker_layout
from app.runtime_engines.gamemaker.runtime_runner import run_exe_smoke, run_html5_fallback
from app.runtime_engines.gamemaker.yyz_parser import extract_yyz_archive, find_yyp_after_extract
from app.runtime_engines.unity.screenshot import compare_runtime_screenshots

logger = logging.getLogger("ai_grader.runtime.gamemaker.verification")


def run_build_pipeline(
    layout: GameMakerLayout,
    *,
    workspace: Path,
    timeout_seconds: int = 90,
) -> Dict[str, Any]:
    """Extract YYZ/YYP and optionally invoke GameMaker IDE CLI build."""
    pipeline: Dict[str, Any] = {
        "version": "gamemaker_build_pipeline_v1",
        "yyz_extracted": False,
        "yyp_ready": bool(layout.yyp_path),
        "ide_build_attempted": False,
        "runnable_after_pipeline": bool(layout.executable or layout.html_entry),
    }

    if layout.yyz_path and not layout.yyp_path:
        extract_dir = workspace / "yyz_extract"
        extract_result = extract_yyz_archive(layout.yyz_path, extract_dir)
        pipeline["yyz_extract"] = extract_result
        if extract_result.get("success"):
            pipeline["yyz_extracted"] = True
            yyp = find_yyp_after_extract(extract_result)
            if yyp:
                layout.yyp_path = yyp
                layout.project_root = yyp.parent
                layout.gml_files = list(yyp.parent.rglob("*.gml"))[:200]
                pipeline["yyp_ready"] = True

    if layout.yyp_path and not (layout.executable or layout.html_entry):
        ide_build = _try_ide_build(layout.yyp_path, workspace, timeout_seconds=timeout_seconds)
        pipeline["ide_build"] = ide_build
        pipeline["ide_build_attempted"] = bool(ide_build.get("attempted"))
        if ide_build.get("executable"):
            layout.executable = Path(str(ide_build["executable"]))
        if ide_build.get("html_entry"):
            layout.html_entry = Path(str(ide_build["html_entry"]))

    refreshed = probe_gamemaker_layout(layout.yyp_path or layout.yyz_path or layout.project_root or workspace)
    if refreshed.executable:
        layout.executable = refreshed.executable
    if refreshed.html_entry:
        layout.html_entry = refreshed.html_entry
    if refreshed.gml_files:
        layout.gml_files = refreshed.gml_files

    pipeline["runnable_after_pipeline"] = bool(layout.executable or layout.html_entry)
    pipeline["layout"] = layout.to_dict()
    return pipeline


def _try_ide_build(yyp_path: Path, workspace: Path, *, timeout_seconds: int) -> Dict[str, Any]:
    """Headless auto-build of source-only GameMaker projects (Igor-based) with install pause."""
    from app.runtime_engines.gamemaker.ide_builder import build_from_source_with_install_pause

    def _on_status(event: str, payload: Dict[str, Any]) -> None:
        """Log pause/resume events during GameMaker install wait."""
        logger.info(
            f"[GAMEMAKER-IDE-BUILD-STATUS] event={event} reason={payload.get('reason')} "
            f"waited={payload.get('resumed_after_install_wait_seconds') or payload.get('wait_exhausted_seconds')}"
        )

    build = build_from_source_with_install_pause(
        yyp_path, workspace, timeout_seconds=max(timeout_seconds, 120), on_status=_on_status
    )
    return {
        "attempted": bool(build.get("attempted")),
        "success": bool(build.get("success")),
        "executable": build.get("executable"),
        "html_entry": None,
        "reason": build.get("reason"),
        "reason_ar": build.get("reason_ar"),
        "tools": build.get("tools"),
        "paused": build.get("paused"),
        "resumed_after_install_wait_seconds": build.get("resumed_after_install_wait_seconds"),
        "wait_exhausted_seconds": build.get("wait_exhausted_seconds"),
    }


def run_gameplay_replay(
    session: RuntimeSession,
    layout: GameMakerLayout,
    *,
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    """Launch runnable build, capture screenshots, compare frame deltas."""
    replay: Dict[str, Any] = {
        "version": "gamemaker_gameplay_replay_v1",
        "method": "none",
        "screenshots": [],
        "comparison": {},
    }

    if layout.executable:
        run_exe_smoke(session, layout.executable, timeout_seconds=timeout_seconds)
        if session.signals.get("runtime_method") == "gamemaker_static_only":
            replay["method"] = "static_only"
            replay["skipped"] = True
            replay["reason"] = (
                (session.signals.get("gamemaker_launch_assessment") or {}).get("skip_reason")
                or "missing_data_win"
            )
        else:
            replay["method"] = "exe_smoke"
    elif layout.html_entry:
        run_html5_fallback(session, layout.html_entry, timeout_seconds=timeout_seconds)
        replay["method"] = "html5_headless"
    else:
        replay["skipped"] = True
        replay["reason"] = "no_runnable_build"
        return replay

    shots = [str(p) for p in session.screenshot_paths]
    replay["screenshots"] = shots
    replay["comparison"] = compare_runtime_screenshots(shots)
    replay["gameplay_observed"] = bool(shots) and replay["comparison"].get("comparison_available", False)
    replay["freeze_detected"] = bool(replay["comparison"].get("freeze_detected"))
    replay["frame_delta_score"] = float(replay["comparison"].get("frame_delta_score") or 0.0)
    return replay


def run_gamemaker_runtime_verification(
    session: RuntimeSession,
    layout: GameMakerLayout,
    *,
    timeout_seconds: int = 90,
) -> Dict[str, Any]:
    """Full PRO verification pipeline."""
    workspace = session.workspace

    build = run_build_pipeline(layout, workspace=workspace, timeout_seconds=timeout_seconds)
    inspection = inspect_gamemaker_objects(layout)
    replay = run_gameplay_replay(session, layout, timeout_seconds=min(45, timeout_seconds))

    artifact = analyze_gamemaker_artifacts(layout)
    gml_mechanics = artifact.get("gml_mechanics") or {}
    static_ids = gml_mechanics.get("detected_ids") or []
    signals = {
        "gamemaker_build_pipeline_ok": build.get("runnable_after_pipeline"),
        "object_inspection_ok": inspection.get("inspection_ok"),
        "object_count": (inspection.get("summary") or {}).get("objects", 0),
        "sprite_count": (inspection.get("summary") or {}).get("sprites", 0),
        "room_count": (inspection.get("summary") or {}).get("rooms", 0),
        "event_count": (inspection.get("summary") or {}).get("events", 0),
        "gameplay_replay_ok": replay.get("gameplay_observed"),
        "screenshot_count": len(replay.get("screenshots") or []),
        "frame_delta_score": replay.get("frame_delta_score", 0.0),
        "freeze_detected": replay.get("freeze_detected", False),
        "functional_smoke_pass": bool(
            build.get("runnable_after_pipeline")
            and inspection.get("inspection_ok")
            and replay.get("gameplay_observed")
            and replay.get("method") in ("exe_smoke", "html5_headless")
        ),
        "static_mechanics_detected": static_ids,
        "static_mechanics_count": len(static_ids),
    }

    result = {
        "success": signals["functional_smoke_pass"] or signals["object_inspection_ok"],
        "method": "gamemaker_pro_runtime_verification",
        "build_pipeline": build,
        "object_inspection": inspection,
        "gameplay_replay": replay,
        "artifact_analysis": artifact,
        "signals": signals,
        "gamemaker_runtime_verification": {
            "version": "gamemaker_runtime_verification_v1",
            "yyp": str(layout.yyp_path) if layout.yyp_path else None,
            "yyz": str(layout.yyz_path) if layout.yyz_path else None,
        },
    }

    session.signals.update(signals)
    session.signals["build_pipeline"] = build
    session.signals["object_inspection"] = inspection
    session.signals["gameplay_replay"] = replay
    session.signals["artifact_analysis"] = artifact
    session.signals["gml_mechanics"] = gml_mechanics
    gm_obs = session.signals.get("gamemaker_observation")
    if isinstance(gm_obs, dict):
        gm_obs["static_mechanics"] = gml_mechanics
    session.signals["gamemaker_runtime_verification"] = result["gamemaker_runtime_verification"]
    session.signals["runtime_method"] = result["method"]

    if replay.get("gameplay_observed"):
        session.status = SessionStatus.COMPLETED
    elif inspection.get("inspection_ok") and build.get("yyp_ready"):
        session.status = SessionStatus.COMPLETED
        session.signals["runtime_partial"] = True
    else:
        session.status = SessionStatus.FAILED if not build.get("yyp_ready") else SessionStatus.COMPLETED

    session.events.record(
        "gamemaker_pro_runtime_verification",
        objects=signals["object_count"],
        rooms=signals["room_count"],
        gameplay=signals["gameplay_replay_ok"],
    )
    return result
