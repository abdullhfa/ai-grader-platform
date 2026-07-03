"""Tests for PlaytestOrchestrator and RequirementVerifier (Task 3)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.gameplay_verifier import (
    CaptureFailureError,
    PlaytestOrchestrator,
    RequirementVerifier,
)
from app.requirement_extractor import (
    DEFAULT_GODOT_EXE_PLAN,
    InputAction,
    RequirementPlan,
    RequirementTest,
)


def _shot(label: str, path: str = "/tmp/a.png", scope: str = "game_window") -> dict:
    return {
        "status": "captured",
        "path": path,
        "label": label,
        "capture_scope": scope,
        "game_window_detected": scope == "game_window",
    }


def test_skips_non_menu_requirements_when_gameplay_not_entered():
    orch = PlaytestOrchestrator(pro_mode=True)
    capture = MagicMock(return_value=_shot("x"))

    package = orch.run(
        artifact_path=Path("game.exe"),
        process_pid=1,
        capture_screenshot=capture,
        plan=DEFAULT_GODOT_EXE_PLAN,
        elapsed_seconds=0.0,
        gameplay_entered=False,
    )

    movement = package.get_result("player_movement")
    assert movement is not None
    assert movement.verified is False
    assert "gameplay_not_entered" in movement.reason
    player_calls = [c for c in capture.call_args_list if c.kwargs.get("requirement_id") == "player_movement"]
    assert not player_calls


def test_desktop_fallback_rejected_in_pro_mode():
    orch = PlaytestOrchestrator(pro_mode=True)
    capture = MagicMock(return_value=_shot("bad", scope="desktop_fallback"))

    plan = RequirementPlan(
        requirements=[
            RequirementTest(
                req_id="player_movement",
                input_sequence=[InputAction("key_hold", "d", duration=0.1)],
                verification_method="pixel_shift_horizontal",
                success_threshold=0.03,
            )
        ]
    )

    with pytest.raises(CaptureFailureError):
        orch.run(
            artifact_path=Path("game.exe"),
            process_pid=1,
            capture_screenshot=capture,
            plan=plan,
            elapsed_seconds=0.0,
            gameplay_entered=True,
        )


def test_jump_not_proxy_from_horizontal_shift(monkeypatch):
    verifier = RequirementVerifier()
    before = _shot("b")
    after = _shot("a")

    monkeypatch.setattr(
        verifier,
        "_horizontal_centroid_shift",
        lambda b, a: 0.5,
    )
    monkeypatch.setattr(
        verifier,
        "_vertical_centroid_shift",
        lambda b, a: 0.01,
    )

    ok_h, _, _ = verifier.verify(
        "pixel_shift_horizontal",
        before,
        after,
        threshold=0.03,
        gameplay_entered=True,
    )
    ok_v, _, _ = verifier.verify(
        "pixel_shift_vertical",
        before,
        after,
        threshold=0.02,
        gameplay_entered=True,
    )

    assert ok_h is True
    assert ok_v is False


def test_orchestrator_tags_screenshots(monkeypatch):
    monkeypatch.setattr("app.gameplay_verifier._key_hold", lambda *a, **k: True)
    monkeypatch.setattr("app.gameplay_verifier._send_key_win", lambda *a, **k: True)
    monkeypatch.setattr("app.gameplay_verifier._click_game_window_center", lambda **k: True)

    calls: list[dict] = []

    def capture(*args, **kwargs):
        shot = _shot(str(kwargs.get("label") or "cap"))
        calls.append(kwargs)
        return shot

    verifier = RequirementVerifier()
    monkeypatch.setattr(
        verifier,
        "verify",
        lambda method, before, after, threshold, gameplay_entered=True: (True, 1.0, "ok"),
    )

    plan = RequirementPlan(
        requirements=[
            RequirementTest(
                req_id="player_movement",
                input_sequence=[InputAction("key_hold", "d", duration=0.1)],
                verification_method="pixel_shift_horizontal",
                success_threshold=0.03,
                btec_criteria=["C.P5"],
            )
        ]
    )

    orch = PlaytestOrchestrator(pro_mode=True, verifier=verifier)
    package = orch.run(
        artifact_path=Path("game.exe"),
        process_pid=None,
        capture_screenshot=capture,
        plan=plan,
        elapsed_seconds=0.0,
        gameplay_entered=True,
    )

    assert package.gameplay_entered is True
    assert package.get_result("player_movement").verified is True
    assert any(c.get("requirement_id") == "player_movement" for c in calls)
    tagged = package.screenshots[0]
    assert tagged.get("requirement_id") == "player_movement"
    assert tagged.get("phase") == "before"
    assert tagged.get("capture_scope") == "game_window"


def test_evidence_package_to_movement_verification():
    orch = PlaytestOrchestrator(pro_mode=False)
    package = orch._package_from_results(
        submission_id="50",
        gameplay_entered=True,
        results=[],
    )
    # manually build via orchestrator internals tested via run - use RequirementResult
    from app.gameplay_verifier import RequirementResult

    package.results = [
        RequirementResult(req_id="player_movement", verified=True, confidence=0.9, btec_criteria=["C.P5"]),
        RequirementResult(req_id="player_jump", verified=True, confidence=0.8, btec_criteria=["C.P5"]),
        RequirementResult(req_id="score_system", verified=False, confidence=0.0, btec_criteria=["C.M3"]),
    ]
    mv = package.to_movement_verification_dict()
    assert mv["player_movement_verified"] is True
    assert mv["jump_detected"] is True
    assert mv["mechanics_verified_count"] == 2
    assert mv["l4_level"] == "L4_partial"
