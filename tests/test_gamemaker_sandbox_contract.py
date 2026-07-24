"""Regression tests: GameMaker EXEs require a real isolated provider."""
from pathlib import Path

from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.gamemaker.runtime_runner import run_exe_smoke
from app.runtime_engines.gamemaker.sandbox_provider import SandboxReadiness
from app.runtime_evidence_package import build_runtime_evidence_package


class _Provider:
    name = "test-sandbox"

    def __init__(self, readiness: SandboxReadiness):
        self._readiness = readiness
        self.launch_calls = 0

    def readiness(self, *, executable: Path, submission_root: Path | None) -> SandboxReadiness:
        return self._readiness

    def launch_and_observe(self, **_kwargs):
        self.launch_calls += 1
        return {"attempted": True, "smoke_result": "launch_ok", "runtime_screenshots": []}


def _session(tmp_path: Path) -> tuple[RuntimeSession, Path]:
    exe = tmp_path / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    return RuntimeSession.create("gamemaker", "demo", tmp_path), exe


def _readiness(*, ready: bool) -> SandboxReadiness:
    return SandboxReadiness(
        "test-sandbox", True, ready, ready, ready, ready, ready,
        "READY" if ready else "RUNTIME_ENVIRONMENT_UNSUPPORTED",
    )


def test_unavailable_provider_skips_without_host_launch(tmp_path: Path):
    session, exe = _session(tmp_path)
    provider = _Provider(_readiness(ready=False))
    result = run_exe_smoke(session, exe, timeout_seconds=5, provider=provider)
    observation = result["observation"]
    assert provider.launch_calls == 0
    assert session.status is SessionStatus.SKIPPED
    assert observation["runtime_status"] == "SKIPPED_UNSUPPORTED_ENVIRONMENT"
    assert observation["runtime_attempted"] is False
    assert observation["game_launch_attempted"] is False
    assert observation["evidence_count"] == 0
    assert observation["academic_runtime_verified"] is False


def test_flag_alone_is_not_a_sandbox_provider(tmp_path: Path, monkeypatch):
    session, exe = _session(tmp_path)
    monkeypatch.setenv("AI_GRADER_WINDOWS_SANDBOX", "1")
    monkeypatch.delenv("AI_GRADER_GAMEMAKER_SANDBOX_ADAPTER", raising=False)
    result = run_exe_smoke(session, exe, timeout_seconds=5)
    assert result["observation"]["runtime_status"] == "SKIPPED_UNSUPPORTED_ENVIRONMENT"
    assert result["observation"]["sandbox_readiness"]["detail"] == "windows_sandbox_adapter_not_configured"


def test_ready_provider_is_the_only_launch_path(tmp_path: Path):
    session, exe = _session(tmp_path)
    provider = _Provider(_readiness(ready=True))
    result = run_exe_smoke(session, exe, timeout_seconds=5, provider=provider)
    assert provider.launch_calls == 1
    assert result["observation"]["game_launch_attempted"] is True


def test_skipped_runtime_has_no_operational_events_or_percentages():
    pkg = build_runtime_evidence_package(
        artifact_inventory={
            "runtime_observation_report": {
                "runtime_status": "SKIPPED_UNSUPPORTED_ENVIRONMENT",
                "status": "completed",
                "game_launch_attempted": False,
                "runtime_screenshots": [],
            }
        }
    )
    assert pkg["runtime_status"] == "SKIPPED"
    assert pkg["events"] == []
    assert pkg["screenshots"] == []
    assert pkg["runtime_evidence_count"] == 0
    assert pkg["runtime_verification"] == "NOT_VERIFIED"
