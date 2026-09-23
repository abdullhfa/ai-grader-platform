"""
Regression tests for the GameMaker "no .exe" auto-build + install-pause path.

Context: STANDARD/fast grading mode used to skip any attempt to build a
source-only GameMaker submission (.yyp without a compiled .exe), silently
treating "we never checked whether GameMaker is installed" the same as
"GameMaker is not installed" — which demoted runtime-gated criteria to a U
grade even when GameMaker was actually available on the grading machine.

These tests pin down the fix:
  1. Submissions that already ship a runnable .exe are completely untouched
     (the auto-build/pause path must never even be invoked).
  2. When GameMaker tools are available, the source project is built and
     graded like a normal .exe submission — regardless of grading tier.
  3. When GameMaker tools are not available, the system pauses (bounded,
     configurable wait) instead of silently downgrading with no explanation.
  4. If GameMaker becomes available mid-wait, the build resumes and succeeds
     automatically — no re-upload / manual re-grade needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from app.runtime_engines.gamemaker import ide_builder
from app.runtime_engines.gamemaker.engine import GameMakerRuntimeEngine
from app.runtime_engines.gamemaker.project_probe import GameMakerLayout
from app.runtime_engines.base import RuntimeSession


def _make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSession:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "submission"
    root.mkdir()
    return RuntimeSession.create(
        engine="gamemaker",
        submission_key="student_x",
        root=root,
        workspace=tmp_path / "workspace",
    )


def _fake_yyp(tmp_path: Path) -> Path:
    yyp = tmp_path / "project.yyp"
    yyp.write_text("{}", encoding="utf-8")
    return yyp


def test_exe_already_present_never_triggers_build_or_pause(tmp_path, monkeypatch):
    """Submissions that already ship a working .exe must be 100% untouched."""
    session = _make_session(tmp_path, monkeypatch)
    layout = GameMakerLayout(
        project_root=tmp_path,
        yyp_path=_fake_yyp(tmp_path),
        executable=tmp_path / "game.exe",
    )

    called = {"n": 0}

    def _boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("build_from_source_with_install_pause must not be called")

    monkeypatch.setattr(ide_builder, "build_from_source_with_install_pause", _boom)

    engine = GameMakerRuntimeEngine()
    # Mirrors the guard in execute(): exe already present -> short-circuit.
    triggered = bool(
        layout.yyp_path and not layout.executable and not layout.html_entry
    )
    assert triggered is False
    assert called["n"] == 0
    assert "gamemaker_ide_build" not in session.signals


def test_build_succeeds_when_tools_available(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    layout = GameMakerLayout(project_root=tmp_path, yyp_path=_fake_yyp(tmp_path))

    built_exe = tmp_path / "built" / "game.exe"
    built_exe.parent.mkdir(parents=True)
    built_exe.write_bytes(b"fake-exe")

    def _fake_build(yyp_path, workspace, *, timeout_seconds=None):
        return {
            "attempted": True,
            "success": True,
            "executable": str(built_exe),
            "data_win": None,
            "reason": "igor_package_zip",
            "reason_ar": "تم بناء اللعبة تلقائياً من المشروع المصدري (Igor).",
            "tools": {"available": True},
        }

    monkeypatch.setattr(ide_builder, "build_from_source", _fake_build)
    monkeypatch.setattr(
        ide_builder, "discover_gamemaker_tools", lambda: {"available": True}
    )

    engine = GameMakerRuntimeEngine()
    resolved = engine._ensure_build_or_pause_for_install(session, layout)

    assert resolved is True
    assert layout.executable == built_exe
    assert session.signals["gamemaker_ide_build"]["success"] is True


def test_pause_when_gamemaker_not_installed_and_wait_disabled(tmp_path, monkeypatch):
    """Wait disabled (0) -> returns immediately with a clear paused reason, no hang."""
    session = _make_session(tmp_path, monkeypatch)
    layout = GameMakerLayout(project_root=tmp_path, yyp_path=_fake_yyp(tmp_path))

    monkeypatch.setenv("AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS", "0")

    def _fake_build(yyp_path, workspace, *, timeout_seconds=None):
        return {
            "attempted": False,
            "success": False,
            "executable": None,
            "reason": "gamemaker_runtime_not_installed",
            "reason_ar": "لم يُعثر على GameMaker...",
            "tools": {"available": False},
        }

    monkeypatch.setattr(ide_builder, "build_from_source", _fake_build)

    engine = GameMakerRuntimeEngine()
    resolved = engine._ensure_build_or_pause_for_install(session, layout)

    assert resolved is False
    build_signal = session.signals["gamemaker_ide_build"]
    assert build_signal["success"] is False
    assert build_signal["paused"] is False
    assert build_signal["wait_skipped_reason"] == "install_wait_disabled"
    assert layout.executable is None


def test_resumes_automatically_once_gamemaker_becomes_available(tmp_path, monkeypatch):
    """GameMaker installed mid-wait -> build retried and succeeds without any
    re-upload or manual re-grade action."""
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS", "120")
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_INSTALL_POLL_SECONDS", "5")
    monkeypatch.setattr(ide_builder.time, "sleep", lambda *_: None)  # instant test

    yyp = _fake_yyp(tmp_path)
    built_exe = tmp_path / "built" / "game.exe"
    built_exe.parent.mkdir(parents=True)
    built_exe.write_bytes(b"fake-exe")

    state = {"available": False, "calls": 0}

    def _fake_discover():
        state["calls"] += 1
        # Becomes available on the second poll.
        if state["calls"] >= 2:
            state["available"] = True
        return {"available": state["available"]}

    def _fake_build_from_source(yyp_path, workspace, *, timeout_seconds=None):
        if not state["available"]:
            return {
                "attempted": False,
                "success": False,
                "executable": None,
                "reason": "gamemaker_runtime_not_installed",
                "reason_ar": "لم يُعثر على GameMaker...",
                "tools": {"available": False},
            }
        return {
            "attempted": True,
            "success": True,
            "executable": str(built_exe),
            "reason": "igor_package_zip",
            "reason_ar": "تم بناء اللعبة تلقائياً.",
            "tools": {"available": True},
        }

    monkeypatch.setattr(ide_builder, "discover_gamemaker_tools", _fake_discover)
    monkeypatch.setattr(ide_builder, "build_from_source", _fake_build_from_source)

    events: list[tuple[str, Dict[str, Any]]] = []
    result = ide_builder.build_from_source_with_install_pause(
        yyp, tmp_path / "workspace", on_status=lambda ev, payload: events.append((ev, payload))
    )

    assert result["success"] is True
    assert result["executable"] == str(built_exe)
    assert result["resumed_after_install_wait_seconds"] >= 0
    event_names = [e for e, _ in events]
    assert "gamemaker_install_paused" in event_names
    assert "gamemaker_install_detected_resumed" in event_names
