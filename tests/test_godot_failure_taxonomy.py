"""Regression tests for Godot runtime failure classification + gate wording +
movement-detection honesty.

Added 2026-07-06 after two production integrity bugs (submission 50 / Ahmad Bakr):
1) capture_preflight_failed was classified NO_VISUAL_RESPONSE_TO_INPUT — blaming
   the student's game for a platform capture fault.
2) _center_band_shift measured TEXTURE not MOTION: identical before/after frames
   scored above the movement/jump thresholds, falsely verifying mechanics and
   opening the C.P5/C.P6 gate (false L4_partial -> unearned grade).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.godot_runtime.failure_taxonomy import (  # noqa: E402
    classify_capture_failure,
    classify_runtime_failure,
)


def _classify(**overrides):
    base = dict(
        window_detected=True,
        black_screen_duration_s=0,
        gameplay_entered=False,
        mechanics_verified_count=0,
        menu_status="",
        visual_response=False,
        server_dialog_detected=False,
        process_crashed=False,
        boot_timed_out=False,
    )
    base.update(overrides)
    return classify_runtime_failure(**base)


class TestCaptureBlindnessIsNotGameFault:
    def test_capture_preflight_failed_classifies_as_capture_failure(self):
        failure = _classify(menu_status="capture_preflight_failed")
        assert failure is not None
        assert failure.code == "GAME_WINDOW_CAPTURE_FAILED"

    def test_capture_failed_status_variants(self):
        for status in ("capture_failed", "game_window_capture_failed", "CAPTURE_PREFLIGHT_FAILED"):
            failure = _classify(menu_status=status)
            assert failure is not None, status
            assert failure.code == "GAME_WINDOW_CAPTURE_FAILED", status

    def test_evidence_preserves_menu_status(self):
        failure = _classify(menu_status="capture_preflight_failed")
        assert failure.evidence["menu_status"] == "capture_preflight_failed"


class TestGenuineFailuresStillClassified:
    def test_genuine_no_visual_response_still_detected(self):
        failure = _classify(menu_status="interaction_done", visual_response=False)
        assert failure.code == "NO_VISUAL_RESPONSE_TO_INPUT"

    def test_menu_stuck_still_menu_not_resolved(self):
        assert _classify(menu_status="main_menu_candidate").code == "MENU_NOT_RESOLVED"

    def test_process_crash_takes_priority(self):
        failure = _classify(menu_status="capture_preflight_failed", process_crashed=True)
        assert failure.code == "PROCESS_CRASHED"

    def test_window_not_found_takes_priority(self):
        failure = _classify(menu_status="capture_preflight_failed", window_detected=False)
        assert failure.code == "WINDOW_NOT_FOUND"

    def test_success_returns_none(self):
        assert _classify(gameplay_entered=True, mechanics_verified_count=2) is None

    def test_entered_no_mechanics(self):
        failure = _classify(gameplay_entered=True, mechanics_verified_count=0)
        assert failure.code == "GAMEPLAY_ENTERED_BUT_NO_MECHANICS"


class TestClassifyCaptureFailureHelper:
    def test_always_returns_capture_failed_code(self):
        failure = classify_capture_failure(
            window_detected=True,
            process_alive=True,
            capture_scope_last="desktop_fallback",
            probe_phase="pre_flight",
        )
        assert failure.code == "GAME_WINDOW_CAPTURE_FAILED"
        assert failure.evidence["probe_phase"] == "pre_flight"


class TestCaptureScopeDegraded:
    """Window lost mid-run (desktop_fallback shots only) must never be blamed
    on the student's game as NO_VISUAL_RESPONSE_TO_INPUT."""

    def test_degraded_flag_forces_capture_failure(self):
        failure = _classify(menu_status="unknown", capture_scope_degraded=True)
        assert failure.code == "GAME_WINDOW_CAPTURE_FAILED"

    def test_crash_still_wins_over_degraded(self):
        failure = _classify(capture_scope_degraded=True, process_crashed=True)
        assert failure.code == "PROCESS_CRASHED"

    def test_not_degraded_keeps_previous_behavior(self):
        failure = _classify(menu_status="interaction_done", capture_scope_degraded=False)
        assert failure.code == "NO_VISUAL_RESPONSE_TO_INPUT"

    def test_helper_detects_desktop_only_run(self):
        from app.gameplay_verifier import _capture_scope_degraded

        shots = [
            {"status": "captured", "capture_scope": "desktop_fallback"},
            {"status": "captured", "capture_scope": "desktop_fallback"},
        ]
        assert _capture_scope_degraded(shots) is True

    def test_helper_ok_when_game_window_present(self):
        from app.gameplay_verifier import _capture_scope_degraded

        shots = [
            {"status": "captured", "capture_scope": "desktop_fallback"},
            {"status": "captured", "capture_scope": "game_window"},
        ]
        assert _capture_scope_degraded(shots) is False

    def test_helper_conservative_without_scope_info(self):
        from app.gameplay_verifier import _capture_scope_degraded

        assert _capture_scope_degraded([{"status": "captured"}]) is False
        assert _capture_scope_degraded([]) is False


class TestStaleNoVisualUpgrade:
    """Report-consistency: a stale NO_VISUAL code in a saved blob must be
    upgraded to GAME_WINDOW_CAPTURE_FAILED when the run's shots are desktop-only,
    so the top summary can never contradict the C.P5 gate note."""

    def test_stale_no_visual_upgraded_when_desktop_only(self):
        from app.gameplay_verifier import _ensure_failure_reason_code_on_negative_gameplay

        gv = {
            "gameplay_entered": False,
            "failure_reason_code": "NO_VISUAL_RESPONSE_TO_INPUT",
            "failure_reason_ar": "لا استجابة بصرية للإدخال بعد burst التفاعل.",
        }
        obs = {
            "runtime_observed": True,
            "runtime_screenshots": [
                {"status": "captured", "capture_scope": "desktop_fallback"},
            ],
        }
        out = _ensure_failure_reason_code_on_negative_gameplay(gv, obs)
        assert out["failure_reason_code"] == "GAME_WINDOW_CAPTURE_FAILED"
        assert out["terminal_classify"] == "capture_pipeline"

    def test_no_visual_kept_when_game_window_was_captured(self):
        from app.gameplay_verifier import _ensure_failure_reason_code_on_negative_gameplay

        gv = {
            "gameplay_entered": False,
            "failure_reason_code": "NO_VISUAL_RESPONSE_TO_INPUT",
        }
        obs = {
            "runtime_screenshots": [
                {"status": "captured", "capture_scope": "game_window"},
            ]
        }
        out = _ensure_failure_reason_code_on_negative_gameplay(gv, obs)
        assert out["failure_reason_code"] == "NO_VISUAL_RESPONSE_TO_INPUT"

    def test_other_codes_never_touched(self):
        from app.gameplay_verifier import _ensure_failure_reason_code_on_negative_gameplay

        gv = {"gameplay_entered": False, "failure_reason_code": "PROCESS_CRASHED"}
        obs = {
            "runtime_screenshots": [
                {"status": "captured", "capture_scope": "desktop_fallback"},
            ]
        }
        out = _ensure_failure_reason_code_on_negative_gameplay(gv, obs)
        assert out["failure_reason_code"] == "PROCESS_CRASHED"


class TestGateReasonWording:
    def test_capture_failure_gets_environment_note(self):
        from app.runtime_evidence_gate import _gate_reason_for

        reason = _gate_reason_for({"failure_reason_code": "GAME_WINDOW_CAPTURE_FAILED"})
        assert "عطل بيئة التقاط" in reason
        assert "لا يدل على خلل في لعبة الطالب" in reason

    def test_capture_preflight_status_gets_environment_note(self):
        from app.runtime_evidence_gate import _gate_reason_for

        reason = _gate_reason_for({"menu_navigation": {"status": "capture_preflight_failed"}})
        assert "عطل بيئة التقاط" in reason

    def test_genuine_game_failure_keeps_standard_reason(self):
        from app.runtime_evidence_gate import _gate_reason_for

        reason = _gate_reason_for({"failure_reason_code": "NO_VISUAL_RESPONSE_TO_INPUT"})
        assert "عطل بيئة التقاط" not in reason
        assert "بوابة التحقق من التشغيل" in reason

    def test_empty_gv_keeps_standard_reason(self):
        from app.runtime_evidence_gate import _gate_reason_for

        assert "عطل بيئة التقاط" not in _gate_reason_for({})


class TestCenterBandShiftHonesty:
    """The false-L4 regression: static frames must never verify movement/jump."""

    @staticmethod
    def _make_textured(tmp_path, name, dx=0, dy=0):
        from PIL import Image

        img = Image.new("L", (480, 360))
        px = img.load()
        for y in range(360):
            for x in range(480):
                px[x, y] = (x * 7 + y * 13) % 200
        if dx or dy:
            img = img.transform((480, 360), Image.AFFINE, (1, 0, -dx, 0, 1, -dy))
        p = tmp_path / name
        img.save(p)
        return str(p)

    def test_identical_textured_frames_score_zero(self, tmp_path):
        from app.gameplay_verifier import _center_band_shift

        a = self._make_textured(tmp_path, "a.png")
        b = self._make_textured(tmp_path, "b.png")
        h, v = _center_band_shift(a, b)
        assert h == 0.0
        assert v == 0.0

    def test_identical_frames_do_not_cross_thresholds(self, tmp_path):
        from app.gameplay_verifier import (
            JUMP_SHIFT_THRESHOLD,
            MOVEMENT_SHIFT_THRESHOLD,
            _center_band_shift,
        )

        a = self._make_textured(tmp_path, "a.png")
        h, v = _center_band_shift(a, a)
        assert h < MOVEMENT_SHIFT_THRESHOLD
        assert v < JUMP_SHIFT_THRESHOLD

    def test_horizontal_translation_detected(self, tmp_path):
        from app.gameplay_verifier import MOVEMENT_SHIFT_THRESHOLD, _center_band_shift

        a = self._make_textured(tmp_path, "a.png")
        b = self._make_textured(tmp_path, "b.png", dx=20)
        h, _v = _center_band_shift(a, b)
        assert h >= MOVEMENT_SHIFT_THRESHOLD

    def test_vertical_translation_detected(self, tmp_path):
        from app.gameplay_verifier import JUMP_SHIFT_THRESHOLD, _center_band_shift

        a = self._make_textured(tmp_path, "a.png")
        b = self._make_textured(tmp_path, "b.png", dy=25)
        _h, v = _center_band_shift(a, b)
        assert v >= JUMP_SHIFT_THRESHOLD
