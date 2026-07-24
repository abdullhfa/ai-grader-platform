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
    # Never auto-launch GameMaker IDE from PATH during teacher batch grading — it opens GUI
    # file dialogs and blocks the session. IDE builds are CI-only when explicitly enabled.
    ide = os.environ.get("AI_GRADER_GAMEMAKER_IDE", "").strip()
    if os.environ.get("AI_GRADER_GAMEMAKER_IDE_BUILD", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"attempted": False, "reason": "gamemaker_ide_build_disabled"}
    if not ide or not Path(ide).is_file():
        return {"attempted": False, "reason": "gamemaker_ide_not_configured"}

    out_dir = workspace / "ide_build"
    out_dir.mkdir(parents=True, exist_ok=True)
    # GameMaker 2024+ CI-style flags vary by license; try common batch patterns.
    cmd_variants = [
        [ide, f"/project={yyp_path}", "/compile", f"/output={out_dir}"],
        [ide, str(yyp_path), "--compile", str(out_dir)],
    ]
    last_err = ""
    for cmd in cmd_variants:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 120),
                cwd=str(yyp_path.parent),
            )
            if proc.returncode == 0:
                exe = next(out_dir.rglob("*.exe"), None) or next(yyp_path.parent.rglob("*.exe"), None)
                html = next(out_dir.rglob("index.html"), None) or next(yyp_path.parent.rglob("index.html"), None)
                return {
                    "attempted": True,
                    "success": True,
                    "command": cmd,
                    "executable": str(exe) if exe else None,
                    "html_entry": str(html) if html else None,
                }
            last_err = (proc.stderr or proc.stdout or "")[-400:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_err = str(exc)

    return {"attempted": True, "success": False, "reason": "ide_build_failed", "detail": last_err}


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
        smoke_result = run_exe_smoke(session, layout.executable, timeout_seconds=timeout_seconds)
        observation = smoke_result.get("observation") or {}
        if observation.get("runtime_status") == "SKIPPED_UNSUPPORTED_ENVIRONMENT":
            replay.update({
                "method": "sandbox_unavailable",
                "skipped": True,
                "reason": observation.get("reason_code"),
                "runtime_status": observation.get("runtime_status"),
                "completion_scope": observation.get("completion_scope"),
                "sandbox_readiness": observation.get("sandbox_readiness") or {},
            })
        elif session.signals.get("runtime_method") == "gamemaker_static_only":
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
        "runtime_status": replay.get("runtime_status") or ("PASS" if replay.get("gameplay_observed") else "NOT_VERIFIED"),
        "runtime_attempted": bool((session.signals.get("gamemaker_observation") or {}).get("runtime_attempted")),
        "game_launch_attempted": bool((session.signals.get("gamemaker_observation") or {}).get("game_launch_attempted")),
        "runtime_gate_passed": bool(replay.get("gameplay_observed")),
        "evidence_count": len(replay.get("screenshots") or []),
        "academic_runtime_verified": bool(replay.get("gameplay_observed")),
        "completion_scope": replay.get("completion_scope") or "RUNTIME_VERIFIED",
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
    session.signals["gamemaker_runtime_verification"] = result["gamemaker_runtime_verification"]
    session.signals["runtime_method"] = result["method"]

    if replay.get("gameplay_observed"):
        session.status = SessionStatus.COMPLETED
    elif replay.get("runtime_status") == "SKIPPED_UNSUPPORTED_ENVIRONMENT":
        # Static inspection succeeded, but no runtime operation occurred.
        session.status = SessionStatus.SKIPPED
        session.signals["completion_scope"] = "COMPLETED_STATIC_ONLY"
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
