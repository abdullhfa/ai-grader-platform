"""Unit tests for Godot runtime failure taxonomy."""
from __future__ import annotations

import pytest

from app.godot_runtime.failure_taxonomy import (
    FAILURE_CODES,
    classify_capture_failure,
    classify_runtime_failure,
)


def test_process_crashed_takes_priority():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="unknown",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=True,
        boot_timed_out=False,
    )
    assert r is not None
    assert r.code == "PROCESS_CRASHED"


def test_server_dependency_block():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=2,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="menu",
        visual_response=False,
        server_dialog_detected=True,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r is not None
    assert r.code == "SERVER_DEPENDENCY_BLOCK"


def test_gameplay_entered_but_no_mechanics():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=True,
        mechanics_verified_count=0,
        menu_status="gameplay_entered",
        visual_response=True,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r is not None
    assert r.code == "GAMEPLAY_ENTERED_BUT_NO_MECHANICS"


def test_boot_timeout():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=30,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="loading",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=True,
    )
    assert r is not None
    assert r.code == "BOOT_TIMEOUT"


def test_window_not_found():
    r = classify_runtime_failure(
        window_detected=False,
        black_screen_duration_s=0,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="unknown",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r is not None
    assert r.code == "WINDOW_NOT_FOUND"


def test_success_returns_none():
    r = classify_runtime_failure(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=True,
        mechanics_verified_count=2,
        menu_status="gameplay_entered",
        visual_response=True,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    assert r is None


@pytest.mark.parametrize(
    "code",
    [c for c in FAILURE_CODES if c != "GAME_WINDOW_CAPTURE_FAILED"],
)
def test_all_codes_have_ar_labels(code: str):
    kwargs = {
        "window_detected": True,
        "black_screen_duration_s": 0,
        "gameplay_entered": False,
        "mechanics_verified_count": 0,
        "menu_status": "unknown",
        "visual_response": False,
        "server_dialog_detected": False,
        "process_crashed": False,
        "boot_timed_out": False,
    }
    if code == "PROCESS_CRASHED":
        kwargs["process_crashed"] = True
    elif code == "SERVER_DEPENDENCY_BLOCK":
        kwargs["server_dialog_detected"] = True
    elif code == "WINDOW_NOT_FOUND":
        kwargs["window_detected"] = False
    elif code == "GAMEPLAY_ENTERED_BUT_NO_MECHANICS":
        kwargs["gameplay_entered"] = True
        kwargs["visual_response"] = True
    elif code == "BOOT_TIMEOUT":
        kwargs["boot_timed_out"] = True
        kwargs["black_screen_duration_s"] = 30
    elif code == "BLACK_SCREEN_PERSISTENT":
        kwargs["black_screen_duration_s"] = 25
        kwargs["menu_status"] = "loading"
    elif code == "MENU_NOT_RESOLVED":
        kwargs["menu_status"] = "menu"
    elif code == "NO_VISUAL_RESPONSE_TO_INPUT":
        kwargs["visual_response"] = False
        kwargs["menu_status"] = "gameplay"
    r = classify_runtime_failure(**kwargs)
    assert r is not None
    assert r.code == code
    assert r.reason_ar


def test_game_window_capture_failed_factory():
    r = classify_capture_failure(
        window_detected=True,
        process_alive=True,
        capture_scope_last="desktop_fallback",
        probe_phase="tagged_capture",
        requirement_id="player_movement",
        phase="before",
    )
    assert r.code == "GAME_WINDOW_CAPTURE_FAILED"
    assert r.reason_ar
    assert r.evidence["capture_scope_last"] == "desktop_fallback"
