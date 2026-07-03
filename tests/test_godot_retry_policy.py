"""Tests for Godot retry policy (mocked nav/play — no real exe)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.godot_runtime.retry_policy import (
    GodotRetryPolicy,
    detect_server_dialog,
    is_godot_runtime_path,
)


def test_is_godot_runtime_path_by_engine_id():
    assert is_godot_runtime_path(Path("game.exe"), engine_id="godot")
    assert not is_godot_runtime_path(Path("game.exe"), engine_id="unity")


def test_is_godot_runtime_path_by_pck_sibling(tmp_path):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"x")
    (tmp_path / "game.pck").write_bytes(b"y")
    assert is_godot_runtime_path(exe)


def test_detect_server_dialog_from_ocr():
    shots = [{"ocr_text": "Connection Failed to server"}]
    assert detect_server_dialog(shots) is True
    assert detect_server_dialog([{"ocr_text": "Play Game"}]) is False


@patch("app.gameplay_verifier.PlaytestOrchestrator")
@patch("app.gameplay_verifier.MenuNavigator")
def test_retry_policy_runs_two_nav_passes_when_first_fails(mock_nav_cls, mock_orch_cls):
    nav1 = MagicMock()
    nav1.gameplay_entered = False
    nav1.status = "stuck_in_menu"
    nav1.visual_state = "menu"
    nav1.to_dict.return_value = {"status": "stuck_in_menu", "log": []}
    nav1.screenshot = None
    nav1.entry_screenshot = None

    nav2 = MagicMock()
    nav2.gameplay_entered = True
    nav2.status = "gameplay_entered"
    nav2.visual_state = "gameplay"
    nav2.to_dict.return_value = {"status": "gameplay_entered", "log": []}
    nav2.screenshot = {"path": "/tmp/x.png", "ocr_text": "score"}
    nav2.entry_screenshot = nav2.screenshot

    mock_nav = mock_nav_cls.return_value
    mock_nav.navigate_to_gameplay.side_effect = [nav1, nav2]
    mock_nav_cls.MAX_ATTEMPTS = 8
    mock_nav_cls.GODOT_BOOT_WAIT = 0.01

    result_mock = MagicMock()
    result_mock.verified = True
    result_mock.req_id = "player_movement"
    result_mock.before_screenshot = None
    result_mock.after_screenshot = None

    pkg1 = MagicMock()
    pkg1.gameplay_entered = False
    pkg1.results = []
    pkg1.screenshots = []
    pkg1.to_movement_verification_dict.return_value = {
        "mechanics_verified_count": 0,
        "player_movement_verified": False,
    }

    pkg2 = MagicMock()
    pkg2.gameplay_entered = True
    pkg2.results = [result_mock]
    pkg2.screenshots = []
    pkg2.to_movement_verification_dict.return_value = {
        "mechanics_verified_count": 1,
        "player_movement_verified": True,
    }

    mock_orch = mock_orch_cls.return_value
    mock_orch.run.side_effect = [pkg1, pkg2]

    outcome = GodotRetryPolicy().run(
        artifact_path=Path("game.exe"),
        process_pid=12345,
        capture_screenshot=lambda *a, **k: {"status": "captured", "capture_scope": "game_window"},
        elapsed_seconds=1.0,
        pro_mode=True,
    )

    assert mock_nav.navigate_to_gameplay.call_count == 2
    assert mock_orch.run.call_count == 2
    assert outcome.gameplay_entered is True
    assert len(outcome.retry_attempts) == 4
    assert outcome.failure is None
