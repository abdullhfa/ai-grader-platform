"""Godot runtime engine — export + student build/PCK smoke + static fallback."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.godot.export_runner import (
    analyze_godot_project,
    build_godot_smoke_observation,
    cleanup_pck_pairing,
    find_godot_project_root,
    find_godot_runnable_artifacts,
    is_godot_editor_executable,
    resolve_godot_binary,
    resolve_pck_exe_pairing,
    run_godot_export,
    run_godot_main_pack_smoke,
)
from app.runtime_engines.registry import register_engine


def _merge_observation(session: RuntimeSession, observation: Dict[str, Any], method: str) -> None:
    session.signals["legacy_observation"] = observation
    session.signals["godot_observation"] = observation
    session.signals["runtime_method"] = method
    session.signals["runtime_evidence_promotion"] = observation.get("runtime_evidence_promotion")
    session.metrics.crash_detected = bool(observation.get("crash_detected"))
    session.metrics.freeze_detected = bool(observation.get("freeze_possible"))
    for shot in observation.get("runtime_screenshots") or []:
        if isinstance(shot, dict) and shot.get("path"):
            session.screenshot_paths.append(Path(str(shot["path"])))
    session.status = (
        SessionStatus.COMPLETED
        if observation.get("status") in ("completed", "partial")
        else SessionStatus.FAILED
    )


@register_engine
class GodotRuntimeEngine(RuntimeEngine):
    engine_id = "godot"
    max_timeout_seconds = 120

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=True,
            supports_build_from_source=True,
            supports_screenshots=True,
            supports_input_simulation=True,
            supports_log_parsing=True,
            supports_telemetry=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        layout = find_godot_runnable_artifacts(root)
        project_root = layout.get("project_root")
        if project_root:
            score = 0.92
            if layout.get("executable") or layout.get("pck"):
                score = 0.97
            return score
        if layout.get("pck") or (root.is_file() and root.suffix.lower() == ".pck"):
            return 0.92
        if root.is_file() and root.suffix.lower() == ".exe":
            if not is_godot_editor_executable(root):
                return 0.85
        return 0.0

    def prepare(self, session: RuntimeSession) -> None:
        layout = find_godot_runnable_artifacts(session.root)
        project_root = layout.get("project_root") or find_godot_project_root(session.root) or session.root
        pairing = resolve_pck_exe_pairing(
            session.root,
            pck=layout.get("pck"),
            donor_exe=layout.get("executable"),
            session_id=session.session_id,
        )
        session.signals["pck_pairing"] = pairing.get("pairing_meta") or {}
        session.signals["project_root"] = str(project_root)
        session.signals["godot_layout"] = {
            "project_root": str(project_root),
            "has_project_godot": (Path(project_root) / "project.godot").is_file(),
            "has_export_presets": (Path(project_root) / "export_presets.cfg").is_file(),
            "student_executable": str(layout["executable"]) if layout.get("executable") else None,
            "student_pck": str(layout["pck"]) if layout.get("pck") else None,
            "paired_executable": str(pairing.get("paired_executable"))
            if pairing.get("paired_executable")
            else None,
        }
        if pairing.get("paired_executable"):
            session.signals["executable"] = str(pairing["paired_executable"])
            session.signals["paired_executable"] = str(pairing["paired_executable"])
        elif layout.get("executable"):
            session.signals["executable"] = str(layout["executable"])
        if pairing.get("pck"):
            session.signals["pck"] = str(pairing["pck"])
        elif layout.get("pck"):
            session.signals["pck"] = str(layout["pck"])

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        project_root = Path(session.signals.get("project_root") or session.root)
        executable = session.signals.get("paired_executable") or session.signals.get("executable")
        pck_path = session.signals.get("pck")
        pairing_meta = session.signals.get("pck_pairing") or {}
        export_result: dict = {}
        pck_smoke: Dict[str, Any] = {}

        if pck_path:
            pck = Path(pck_path)
            pck_smoke = run_godot_main_pack_smoke(
                pck,
                timeout_seconds=min(timeout_seconds, 45),
            )
            session.signals["pck_smoke"] = pck_smoke
            session.events.record(
                "godot_pck_smoke",
                source="godot_engine",
                success=bool(pck_smoke.get("success")),
                pck=str(pck),
            )

        if executable and not is_godot_editor_executable(Path(executable)):
            from app.runtime_observation_sandbox import (
                resolve_smoke_timeout_seconds,
                smoke_test_windows_exe,
            )

            _gm = session.signals.get("grading_mode")
            smoke = smoke_test_windows_exe(
                Path(executable),
                timeout=resolve_smoke_timeout_seconds(_gm),
                capture_screenshots=True,
                enable_interaction_trace=True,
                session_ctx={
                    "runtime_session_id": session.session_id,
                    "student_name": session.submission_key,
                },
                grading_mode=_gm,
            )
            observation = build_godot_smoke_observation(
                smoke,
                pairing_meta=pairing_meta,
                pck_smoke=pck_smoke,
                pck_path=Path(pck_path) if pck_path else None,
            )
            method = "godot_pck_pairing_smoke"
            if pck_smoke.get("success"):
                method = "godot_main_pack_smoke"
            _merge_observation(session, observation, method)
            return

        if not executable and not pck_path:
            export_result = run_godot_export(
                project_root,
                timeout_seconds=min(timeout_seconds * 2, 300),
            )
            session.signals["export_attempt"] = export_result
            session.events.record(
                "godot_export_attempt",
                source="godot_engine",
                success=bool(export_result.get("success")),
                presets_tried=export_result.get("presets_tried") or [],
            )
            if export_result.get("artifact"):
                executable = export_result["artifact"]
                session.signals["executable"] = executable
                from app.runtime_observation_sandbox import (
                    resolve_smoke_timeout_seconds,
                    smoke_test_windows_exe,
                )

                _gm = session.signals.get("grading_mode")
                smoke = smoke_test_windows_exe(
                    Path(executable),
                    timeout=resolve_smoke_timeout_seconds(_gm),
                    capture_screenshots=True,
                    enable_interaction_trace=True,
                    session_ctx={
                        "runtime_session_id": session.session_id,
                        "student_name": session.submission_key,
                    },
                    grading_mode=_gm,
                )
                observation = build_godot_smoke_observation(smoke, pairing_meta=pairing_meta)
                _merge_observation(session, observation, "godot_exe_smoke")
                return

        if pck_smoke.get("success"):
            observation = build_godot_smoke_observation(
                {"attempted": False, "smoke_result": "launch_ok", "runtime_screenshots": []},
                pairing_meta=pairing_meta,
                pck_smoke=pck_smoke,
                pck_path=Path(pck_path) if pck_path else None,
            )
            _merge_observation(session, observation, "godot_main_pack_smoke")
            return

        apk_pck_paths = [
            p
            for p in session.root.rglob("*")
            if p.is_file() and p.suffix.lower() in {".apk", ".pck"}
        ]
        if apk_pck_paths:
            from app.runtime_observation_sandbox import observe_runtime_artifacts

            scan_paths = [str(p) for p in apk_pck_paths[:6]]
            obs = observe_runtime_artifacts(
                scan_paths,
                enable_smoke_test=False,
                student_name=session.submission_key,
            )
            obs["observation_mode"] = "godot_apk_pck_static_scan"
            obs["runtime_method"] = "godot_apk_pck_static_scan"
            obs["game_launch_attempted"] = False
            obs["runtime_verified"] = False
            obs["godot_binary_configured"] = bool(resolve_godot_binary())
            obs["status"] = "partial"
            obs["observation_summary_ar"] = (
                "تم فحص APK/PCK هيكلياً فقط — اللعبة لم تُشغَّل على الخادم. "
                "لتشغيل Godot: اضبط AI_GRADER_GODOT_BIN أو أرفق ملف .exe مصاحب للـ .pck "
                "أو فعّل أتمتة Android في PRO."
            )
            _merge_observation(session, obs, "godot_apk_pck_static_scan")
            return

        static = export_result.get("static_analysis") or analyze_godot_project(project_root)
        session.signals["godot_project_analysis"] = static
        observation = {
            "status": "partial",
            "observation_mode": "godot_static_analysis",
            "runtime_method": "godot_static_analysis",
            "game_launch_attempted": False,
            "runtime_verified": False,
            "runtime_observed": False,
            "godot_binary_configured": bool(resolve_godot_binary()),
            "observation_summary_ar": (
                "تحليل Godot ثابت فقط — لا project.godot ولا تشغيل. "
                "اضبط AI_GRADER_GODOT_BIN أو أرفق build قابل للتشغيل."
            ),
            "godot_project_analysis": static,
        }
        _merge_observation(session, observation, "godot_static_analysis")
        session.events.record(
            "godot_static_analysis",
            source="godot_engine",
            script_count=static.get("script_count", 0),
            scene_count=static.get("scene_count", 0),
        )
        if not static.get("godot_binary_configured") and not static.get("runnable_build_present"):
            session.errors.append("no_godot_executable_or_export")

    def cleanup(self, session: RuntimeSession) -> None:
        cleanup_pck_pairing(session.signals.get("pck_pairing"))
