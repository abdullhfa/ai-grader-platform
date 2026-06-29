"""GameMaker runtime verification engine — PRO build + gameplay replay."""
from __future__ import annotations

import os
from pathlib import Path

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.gamemaker.build_runner import analyze_gamemaker_artifacts
from app.runtime_engines.gamemaker.log_parser import parse_gamemaker_log_file
from app.runtime_engines.gamemaker.project_probe import (
    detect_gamemaker_confidence,
    load_yyp_metadata,
    probe_gamemaker_layout,
)
from app.runtime_engines.gamemaker.runtime_verification import run_gamemaker_runtime_verification
from app.runtime_engines.gamemaker.yyz_parser import extract_yyz_archive, find_yyp_after_extract
from app.runtime_engines.registry import register_engine


def _env_static_only() -> bool:
    return os.environ.get("AI_GRADER_GAMEMAKER_STATIC_ONLY", "").lower() in ("1", "true", "yes", "on")


@register_engine
class GameMakerRuntimeEngine(RuntimeEngine):
    engine_id = "gamemaker"
    max_timeout_seconds = 120

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=False,
            supports_input_simulation=True,
            supports_screenshots=True,
            supports_log_parsing=True,
            supports_telemetry=True,
            supports_build_from_source=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        return detect_gamemaker_confidence(root)

    def prepare(self, session: RuntimeSession) -> None:
        layout = probe_gamemaker_layout(session.root)
        session.signals["gamemaker_layout"] = layout.to_dict()

        if layout.yyz_path and not layout.yyp_path:
            extract_dir = session.workspace / "yyz_extract"
            extract_result = extract_yyz_archive(layout.yyz_path, extract_dir)
            session.signals["yyz_extract"] = extract_result
            if extract_result.get("success"):
                yyp = find_yyp_after_extract(extract_result)
                if yyp:
                    layout = probe_gamemaker_layout(yyp.parent)
                    session.root = yyp.parent
                    session.signals["gamemaker_layout"] = layout.to_dict()

        if layout.yyp_path:
            session.signals["yyp_metadata"] = load_yyp_metadata(layout.yyp_path)

        session._gm_layout = layout

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        layout = getattr(session, "_gm_layout", None) or probe_gamemaker_layout(session.root)
        pro_runtime = bool(session.signals.get("enable_gamemaker_runtime_verification"))
        static_only = (not pro_runtime) or _env_static_only()

        if pro_runtime and not static_only:
            run_gamemaker_runtime_verification(
                session,
                layout,
                timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
            )
            return

        analysis = analyze_gamemaker_artifacts(layout)
        session.signals["artifact_analysis"] = analysis
        session.signals["runtime_method"] = "gamemaker_artifact_analysis"
        session.status = SessionStatus.COMPLETED
        session.events.record(
            "gamemaker_artifact_analysis",
            gml_files=len(layout.gml_files),
            yyp=bool(layout.yyp_path),
            static_only=True,
        )
        for log_name in ("output_log.txt", "debug.log", "log.txt"):
            for log_path in (layout.project_root or session.root).rglob(log_name):
                parsed = parse_gamemaker_log_file(log_path)
                if parsed.get("ok"):
                    session.signals["log_parse"] = parsed
                    session.log_paths.append(log_path)
                break
