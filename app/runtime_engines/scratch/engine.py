"""Scratch runtime verification engine — PRO graph + VM; BASIC static graph."""
from __future__ import annotations

import os
from pathlib import Path

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.registry import register_engine
from app.runtime_engines.scratch.project_probe import detect_scratch_confidence, find_scratch_project
from app.runtime_engines.scratch.runtime_verification import (
    run_scratch_runtime_verification,
    run_scratch_static_graph,
)


def _env_static_only() -> bool:
    return os.environ.get("AI_GRADER_SCRATCH_STATIC_ONLY", "").lower() in ("1", "true", "yes", "on")


@register_engine
class ScratchRuntimeEngine(RuntimeEngine):
    engine_id = "scratch"
    max_timeout_seconds = 35

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=True,
            supports_input_simulation=False,
            supports_screenshots=False,
            supports_log_parsing=True,
            supports_telemetry=True,
            supports_build_from_source=False,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        return detect_scratch_confidence(root)

    def prepare(self, session: RuntimeSession) -> None:
        sb3 = find_scratch_project(session.root)
        if not sb3:
            session.status = SessionStatus.SKIPPED
            session.errors.append("no_scratch_project")
            return
        session.signals["scratch_sb3"] = str(sb3)
        session._scratch_sb3 = sb3

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        sb3 = getattr(session, "_scratch_sb3", None) or find_scratch_project(session.root)
        if not sb3:
            session.status = SessionStatus.SKIPPED
            return

        pro_runtime = bool(session.signals.get("enable_scratch_runtime_verification"))
        static_only = (not pro_runtime) or _env_static_only()

        if pro_runtime and not static_only:
            run_scratch_runtime_verification(
                session,
                sb3,
                timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
            )
            return

        run_scratch_static_graph(session, sb3)

    def collect_evidence(self, session: RuntimeSession) -> dict:
        base = super().collect_evidence(session)
        base["scratch_execution_graph"] = session.signals.get("execution_graph")
        base["scratch_vm"] = session.signals.get("scratch_vm")
        return base
