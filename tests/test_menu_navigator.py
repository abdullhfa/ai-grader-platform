"""Tests for MenuNavigator visual state classifier (Task 2)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.gameplay_verifier import MenuNavigator, MenuNavigationResult, run_automated_gameplay_verification


def test_classify_visual_state_gameplay_hud_no_menu():
    nav = MenuNavigator()
    state = nav.classify_visual_state(
        {"visual_state": "gameplay_candidate", "ocr_text": "score: 42 lives: 3"}
    )
    assert state == "gameplay"


def test_classify_visual_state_menu_play_keyword():
    nav = MenuNavigator()
    state = nav.classify_visual_state(
        {"visual_state": "main_menu_candidate", "ocr_text": "press start to play"}
    )
    assert state == "menu"


def test_classify_visual_state_loading_screen():
    nav = MenuNavigator()
    state = nav.classify_visual_state({"visual_state": "loading_screen", "ocr_text": ""})
    assert state == "loading"


def test_classify_visual_state_unknown_without_signals():
    nav = MenuNavigator()
    state = nav.classify_visual_state({"visual_state": "", "ocr_text": "options credits"})
    assert state == "unknown"


def test_navigate_returns_gameplay_entered_on_gameplay_screen(monkeypatch):
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **kwargs: None)
    nav = MenuNavigator(max_attempts=3)
    shots = [
        {"status": "captured", "path": "", "visual_state": "gameplay_candidate", "ocr_text": "score: 1"},
    ]
    capture = MagicMock(side_effect=shots)

    result = nav.navigate_to_gameplay(
        artifact_path=Path("game.exe"),
        process_pid=1234,
        capture_screenshot=capture,
        elapsed_seconds=1.0,
    )

    assert isinstance(result, MenuNavigationResult)
    assert result.status == "gameplay_entered"
    assert result.gameplay_entered is True
    assert result.attempts in (0, 1)
    assert result.visual_state == "gameplay"


def test_navigate_waits_for_black_screen_boot(monkeypatch):
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **kwargs: None)
    monkeypatch.setattr("app.gameplay_verifier._click_game_window_center", lambda **kwargs: True)
    monkeypatch.setattr("app.gameplay_verifier._send_key_win", lambda *a, **k: True)
    monkeypatch.setattr("app.gameplay_verifier.MenuNavigator.GODOT_BOOT_WAIT", 0.01)
    monkeypatch.setattr("app.gameplay_verifier.MenuNavigator.BOOT_POLL_INTERVAL", 0.01)

    nav = MenuNavigator(max_attempts=2)
    black = {
        "status": "captured",
        "path": "",
        "visual_state": "black_screen",
        "visual_stats": {"black_screen_possible": True, "avg_luma_approx": 2.0},
        "ocr_text": "",
    }
    gameplay = {
        "status": "captured",
        "path": "",
        "visual_state": "gameplay_candidate",
        "ocr_text": "score: 10",
    }
    capture = MagicMock(side_effect=[black, black, gameplay])

    result = nav.navigate_to_gameplay(
        artifact_path=Path("game.exe"),
        process_pid=1234,
        capture_screenshot=capture,
        elapsed_seconds=0.0,
    )

    assert result.gameplay_entered is True
    assert capture.call_count >= 3


def test_is_black_screen_from_visual_stats():
    nav = MenuNavigator()
    assert nav._is_black_screen(
        {"visual_state": "black_screen", "visual_stats": {"black_screen_possible": True}}
    )
    assert not nav._is_black_screen(
        {"visual_state": "gameplay_candidate", "visual_stats": {"avg_luma_approx": 120.0}}
    )


def test_navigate_stuck_in_menu_after_max_attempts(monkeypatch):
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **kwargs: None)
    monkeypatch.setattr("app.gameplay_verifier._click_game_window_center", lambda **kwargs: True)
    monkeypatch.setattr("app.gameplay_verifier._send_key_win", lambda *a, **k: True)
    nav = MenuNavigator(max_attempts=2)
    menu_shot = {
        "status": "captured",
        "path": "",
        "visual_state": "main_menu_candidate",
        "ocr_text": "main menu start",
    }
    capture = MagicMock(return_value=menu_shot)

    result = nav.navigate_to_gameplay(
        artifact_path=Path("game.exe"),
        process_pid=None,
        capture_screenshot=capture,
        elapsed_seconds=0.0,
    )

    assert result.status == "stuck_in_menu"
    assert result.gameplay_entered is False
    assert result.attempts == 2


def test_detect_and_enter_gameplay_dict_compat(monkeypatch):
    monkeypatch.setattr("app.window_focus_manager.focus_game_window", lambda **kwargs: None)
    nav = MenuNavigator()
    shots = [
        {"status": "captured", "path": "", "visual_state": "gameplay_candidate", "ocr_text": "points: 5"},
    ]
    capture = MagicMock(side_effect=shots)
    row = nav.detect_and_enter_gameplay(
        artifact_path=Path("x.exe"),
        process_pid=None,
        capture_screenshot=capture,
        elapsed_seconds=0.0,
    )
    assert row["status"] == "gameplay_entered"
    assert row["gameplay_entered"] is True


def test_movement_not_verified_when_menu_navigation_fails(monkeypatch):
    monkeypatch.setattr(
        "app.gameplay_verifier.MenuNavigator.navigate_to_gameplay",
        lambda self, **kwargs: __import__(
            "app.gameplay_verifier", fromlist=["MenuNavigationResult"]
        ).MenuNavigationResult(
            status="stuck_in_menu",
            attempts=5,
            gameplay_entered=False,
            visual_state="menu",
        ),
    )

    report = run_automated_gameplay_verification(
        artifact_path=Path("game.exe"),
        process_pid=1,
        capture_screenshot=MagicMock(return_value={"status": "captured", "path": "", "capture_scope": "game_window"}),
        elapsed_seconds=0.0,
    )

    assert report["gameplay_entered"] is False
    assert report["player_movement_verified"] is False
    assert report["jump_detected"] is False
    assert report["l4_level"] == "L3"
