"""GameMaker runtime verification engine — PRO build + gameplay replay."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

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

    def _ensure_build_or_pause_for_install(self, session: RuntimeSession, layout) -> bool:
        """
        No compiled build shipped with this submission (no .exe / data.win /
        html5 export) — always try to build the source project with the
        GameMaker IDE (Igor), regardless of STANDARD vs PRO grading tier.

        This runs unconditionally (not gated behind
        ``enable_gamemaker_runtime_verification``) because skipping it in
        STANDARD/fast mode was silently treating "we never checked" the same
        as "GameMaker isn't installed" — demoting runtime-gated criteria to a
        U grade even when GameMaker was actually available on the grading
        machine. If GameMaker genuinely isn't installed yet (Windows-only
        tool), this pauses and re-polls for a bounded window so the build
        + grading resumes automatically the moment it's installed.

        Completely inert — never called — when the submission already ships
        a runnable .exe/html5 build; that path is untouched.
        """
        from app.runtime_engines.gamemaker.ide_builder import (
            build_from_source_with_install_pause,
        )

        print(
            f"🎮 [GAMEMAKER-NO-EXE] submission={session.submission_key} "
            f"yyp={layout.yyp_path} — no .exe/html5 shipped, attempting "
            f"auto-build via GameMaker IDE (this print only appears if the "
            f"new install-check code is actually loaded and reached)"
        )

        def _on_status(event: str, payload: Dict[str, Any]) -> None:
            print(
                f"🎮 [GAMEMAKER-INSTALL-GATE] submission={session.submission_key} "
                f"event={event} reason={payload.get('reason')!r} "
                f"waited={payload.get('resumed_after_install_wait_seconds') or payload.get('wait_exhausted_seconds')}"
            )
            try:
                session.events.record(
                    event,
                    reason=payload.get("reason"),
                    reason_ar=payload.get("reason_ar"),
                    waited_seconds=payload.get("resumed_after_install_wait_seconds")
                    or payload.get("wait_exhausted_seconds"),
                )
            except Exception:
                pass

        build = build_from_source_with_install_pause(
            layout.yyp_path,
            session.workspace,
            on_status=_on_status,
        )
        session.signals["gamemaker_ide_build"] = build
        print(
            f"🎮 [GAMEMAKER-BUILD-RESULT] submission={session.submission_key} "
            f"success={build.get('success')} reason={build.get('reason')!r} "
            f"executable={build.get('executable')} tools={build.get('tools')}"
        )
        if build.get("success") and build.get("executable"):
            exe_path = Path(str(build["executable"]))
            if exe_path.is_file():
                layout.executable = exe_path
                return True
        return False

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        layout = getattr(session, "_gm_layout", None) or probe_gamemaker_layout(session.root)
        pro_runtime = bool(session.signals.get("enable_gamemaker_runtime_verification"))
        env_static_only = _env_static_only()

        freshly_built = False
        if layout.yyp_path and not layout.executable and not layout.html_entry and not env_static_only:
            freshly_built = self._ensure_build_or_pause_for_install(session, layout)

        if (pro_runtime or freshly_built) and not env_static_only:
            run_gamemaker_runtime_verification(
                session,
                layout,
                timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
            )
            return

        analysis = analyze_gamemaker_artifacts(layout)
        session.signals["artifact_analysis"] = analysis
        session.signals["gml_mechanics"] = analysis.get("gml_mechanics") or {}
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
