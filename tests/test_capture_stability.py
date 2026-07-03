"""Tests for submission 50 PRO game-window capture stability (spec §10.1)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.gameplay_verifier import CaptureFailureError, PlaytestOrchestrator, build_capture_failure_gv
from app.godot_runtime.failure_taxonomy import FAILURE_CODES, classify_capture_failure
from app.godot_runtime.retry_policy import GodotRetryPolicy


def _game_window_shot() -> dict:
    return {"status": "captured", "capture_scope": "game_window"}


def _desktop_fallback_shot() -> dict:
    return {"status": "captured", "capture_scope": "desktop_fallback"}


def test_failure_taxonomy_includes_game_window_capture_failed():
    assert "GAME_WINDOW_CAPTURE_FAILED" in FAILURE_CODES
    failure = classify_capture_failure(
        window_detected=True,
        process_alive=True,
        capture_scope_last="desktop_fallback",
        probe_phase="pre_flight",
    )
    assert failure.code == "GAME_WINDOW_CAPTURE_FAILED"
    assert failure.reason_ar


@patch("app.window_focus_manager.focus_game_window")
def test_capture_tagged_retries_before_evidence_error(_focus):
    calls = {"n": 0}

    def capture(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            return _desktop_fallback_shot()
        return _game_window_shot()

    orch = PlaytestOrchestrator(pro_mode=True)
    shot = orch._capture_tagged(
        artifact_path=Path("game.exe"),
        process_pid=999,
        capture_screenshot=capture,
        req_id="player_movement",
        phase="before",
        elapsed_seconds=1.0,
    )
    assert shot["capture_scope"] == "game_window"
    assert calls["n"] == 3


@patch("app.window_focus_manager.focus_game_window")
def test_capture_tagged_exhausted_raises_capture_failure_error(_focus):
    capture = MagicMock(return_value=_desktop_fallback_shot())
    orch = PlaytestOrchestrator(pro_mode=True)
    with pytest.raises(CaptureFailureError) as exc_info:
        orch._capture_tagged(
            artifact_path=Path("game.exe"),
            process_pid=999,
            capture_screenshot=capture,
            req_id="player_movement",
            phase="before",
            elapsed_seconds=1.0,
        )
    assert exc_info.value.requirement_id == "player_movement"
    assert capture.call_count == 3


@patch("app.gameplay_verifier.PlaytestOrchestrator")
@patch("app.gameplay_verifier.MenuNavigator")
@patch("app.window_focus_manager.focus_game_window")
def test_capture_preflight_fails_with_game_window_capture_failed(
    _focus,
    mock_nav_cls,
    mock_orch_cls,
):
    mock_nav_cls.MAX_ATTEMPTS = 8
    outcome = GodotRetryPolicy().run(
        artifact_path=Path("game.exe"),
        process_pid=12345,
        capture_screenshot=lambda *a, **k: _desktop_fallback_shot(),
        elapsed_seconds=1.0,
        pro_mode=True,
    )
    assert mock_nav_cls.return_value.navigate_to_gameplay.call_count == 0
    assert mock_orch_cls.return_value.run.call_count == 0
    assert outcome.gameplay_entered is False
    assert outcome.failure is not None
    assert outcome.failure.code == "GAME_WINDOW_CAPTURE_FAILED"
    assert outcome.retry_attempts[0]["step"] == "capture_preflight"


def test_sandbox_maps_capture_failure_not_no_visual():
    from app.runtime_observation_sandbox import _attach_terminal_godot_classify_if_missing

    exc = CaptureFailureError(
        "game_window capture failed for player_movement/before — "
        "desktop_fallback not permitted in PRO mode",
        requirement_id="player_movement",
        phase="before",
        capture_scope_last="desktop_fallback",
    )
    gv = build_capture_failure_gv(exc, process_pid=1234)
    assert gv["failure_reason_code"] == "GAME_WINDOW_CAPTURE_FAILED"
    assert gv["terminal_classify"] == "capture_pipeline"

    out = {
        "gameplay_verification": gv,
        "interaction_trace": {"errors": [str(exc)]},
        "runtime_screenshots": [{"status": "captured"}],
        "smoke_result": "stable_window",
        "signals": {},
    }
    _attach_terminal_godot_classify_if_missing(
        out,
        Path("game.exe"),
        interaction_ran=True,
        session_ctx={"engine": "godot"},
        grading_mode="deep",
        enable_interaction_trace=True,
    )
    assert out["gameplay_verification"]["failure_reason_code"] == "GAME_WINDOW_CAPTURE_FAILED"
    assert out["gameplay_verification"]["failure_reason_code"] != "NO_VISUAL_RESPONSE_TO_INPUT"
