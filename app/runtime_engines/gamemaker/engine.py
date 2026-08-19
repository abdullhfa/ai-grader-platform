"""GameMaker runtime engine.

The engine deliberately routes source-only submissions through the same runtime
verification path as submissions that already contain an executable. A
successful Igor build is an intermediate artifact, not runtime evidence.
"""
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
from app.runtime_engines.gamemaker.runtime_verification import (
    run_gamemaker_runtime_verification,
)
from app.runtime_engines.gamemaker.yyz_parser import extract_yyz_archive, find_yyp_after_extract
from app.runtime_engines.registry import register_engine


def _env_static_only() -> bool:
    return os.environ.get("AI_GRADER_GAMEMAKER_STATIC_ONLY", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
        submission_version_evidence = dict(layout.version_evidence)
        session.signals["gamemaker_layout"] = layout.to_dict()

        if layout.yyz_path and not layout.yyp_path:
            extract_dir = session.workspace / "yyz_extract"
            extract_result = extract_yyz_archive(layout.yyz_path, extract_dir)
            session.signals["yyz_extract"] = extract_result
            if extract_result.get("success"):
                yyp = find_yyp_after_extract(extract_result)
                if yyp:
                    layout = probe_gamemaker_layout(yyp.parent)
                    if submission_version_evidence:
                        layout.version_evidence = submission_version_evidence
                    session.root = yyp.parent
                    session.signals["gamemaker_layout"] = layout.to_dict()

        if layout.yyp_path:
            session.signals["yyp_metadata"] = load_yyp_metadata(layout.yyp_path)

        session._gm_layout = layout

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        layout = getattr(session, "_gm_layout", None) or probe_gamemaker_layout(session.root)
        source_only = bool(layout.yyp_path and not layout.executable and not layout.html_entry)
        requested_runtime = bool(session.signals.get("enable_gamemaker_runtime_verification"))
        static_only = _env_static_only()

        # A source-only submission must not be considered complete merely because
        # Igor returned exit code 0. The build is only an intermediate artifact;
        # the shared runtime verifier must launch/observe it and populate evidence.
        # The explicit environment escape hatch remains available for deterministic
        # static tests that intentionally do not have a Windows runtime installed.
        if (source_only or requested_runtime) and not static_only:
            session.signals["source_only_runtime_verification_requested"] = source_only
            session.events.record(
                "gamemaker_runtime_verification_start",
                source_only=source_only,
                yyp=str(layout.yyp_path) if layout.yyp_path else None,
            )
            verification = run_gamemaker_runtime_verification(
                session,
                layout,
                timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
            )
            session.signals["gamemaker_runtime_verification_result"] = verification
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
                try:
                    parsed = parse_gamemaker_log_file(log_path)
                    if parsed.get("ok"):
                        session.signals["log_parse"] = parsed
                        session.log_paths.append(log_path)
                        break
                except Exception:
                    pass


__all__ = ["GameMakerRuntimeEngine"]


def _runtime_verification_entrypoint_present() -> bool:
    """Keep a tiny import-level sentinel for regression tests and diagnostics."""
    return callable(run_gamemaker_runtime_verification)


assert _runtime_verification_entrypoint_present()

# End of module.

# Notes:
# - Build success is never treated as gameplay evidence.
# - Source-only projects use the same verifier as executable submissions.
# - Static-only behavior is opt-in for tests and offline inspection.

def _engine_contract_marker() -> str:
    """Return a stable marker for import and regression diagnostics."""
    return "gamemaker_runtime_handoff_v1"


assert _engine_contract_marker() == "gamemaker_runtime_handoff_v1"

__all__.append("_engine_contract_marker")

# Keep module-level imports and registration deterministic for worker startup.


def _source_only_requires_runtime(layout) -> bool:
    """Return whether a layout has source but no directly runnable artifact."""
    return bool(layout.yyp_path and not layout.executable and not layout.html_entry)


__all__.append("_source_only_requires_runtime")


# The helper is intentionally side-effect free and is used by regression tests.


def _static_mode_enabled() -> bool:
    return _env_static_only()


__all__.append("_static_mode_enabled")


# End of stable compatibility helpers.
