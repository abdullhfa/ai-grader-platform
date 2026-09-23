"""Tests for the Feature-First Evidence Architecture (mandate 2026-07-07).

Locks the 8 rules: static existence vs runtime execution as independent
states; wording never claims runtime success; capture failure never erases
static evidence; deterministic output.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.godot_feature_evidence import (  # noqa: E402
    build_feature_evidence,
    merge_runtime_states,
    scan_godot_project,
)


def _mini_project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    (root / "scripts").mkdir(parents=True)
    (root / "scenes").mkdir()
    (root / "scripts" / "player.gd").write_text(
        "extends CharacterBody2D\n"
        "const JUMP_FORCE = -400\n"
        "var lives = 3\n"
        "var score = 0\n"
        "func _physics_process(delta):\n"
        "    velocity.y += gravity * delta\n"
        "    if Input.is_action_just_pressed(\"ui_accept\"):\n"
        "        velocity.y = JUMP_FORCE\n"
        "    velocity.x = direction * SPEED\n"
        "    move_and_slide()\n",
        encoding="utf-8",
    )
    (root / "scenes" / "Player.tscn").write_text(
        '[node name="Player" type="CharacterBody2D"]\n'
        '[node name="Shape" type="CollisionShape2D" parent="."]\n'
        '[node name="Anim" type="AnimatedSprite2D" parent="."]\n',
        encoding="utf-8",
    )
    (root / "project.godot").write_text(
        "[application]\nconfig/name=\"MiniGame\"\n\n"
        "[input]\nui_accept={}\nmove_left={}\nmove_right={}\n",
        encoding="utf-8",
    )
    return root


def _feat(matrix, fid):
    return next(f for f in matrix["features"] if f["feature_id"] == fid)


class TestStaticExistence:
    def test_jump_detected_with_line_evidence_and_input_map(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        jump = _feat(matrix, "jump")
        assert jump["implementation"] == "IMPLEMENTED"
        assert any(
            e["file"].endswith("player.gd") and "JUMP_FORCE" in e["snippet"]
            for e in jump["evidence"]
        )
        assert "ui_accept" in jump["input_actions"]
        assert jump["implementation_confidence"] >= 80

    def test_movement_lives_score_gravity_detected(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        for fid in ("player_movement", "lives_health", "score", "gravity", "collision"):
            assert _feat(matrix, fid)["implementation"] == "IMPLEMENTED", fid

    def test_absent_feature_reported_not_found(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        save = _feat(matrix, "save_system")
        assert save["implementation"] == "NOT_FOUND"
        assert save["implementation_confidence"] == 0

    def test_wording_never_claims_runtime_success(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        for f in matrix["features"]:
            assert "works" not in f["statement_en"].lower()
            assert "يعمل" not in f["statement_ar"]
            if f["implementation"] == "IMPLEMENTED":
                assert "implementation detected" in f["statement_en"]

    def test_deterministic(self, tmp_path):
        root = _mini_project(tmp_path)
        assert scan_godot_project(root) == scan_godot_project(root)


class TestEvidenceSources:
    def test_jump_sources_include_code_and_input_map(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        jump = _feat(matrix, "jump")
        assert "code" in jump["evidence_sources"]
        assert "input_map" in jump["evidence_sources"]

    def test_collision_sources_include_scene(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        assert "scene" in _feat(matrix, "collision")["evidence_sources"]

    def test_absent_feature_has_no_sources(self, tmp_path):
        matrix = scan_godot_project(_mini_project(tmp_path))
        assert _feat(matrix, "save_system")["evidence_sources"] == []

    def test_implementation_never_uses_pass_terminology(self, tmp_path):
        # Pearson reports reserve PASS for criterion achievement.
        matrix = scan_godot_project(_mini_project(tmp_path))
        for f in matrix["features"]:
            assert f["implementation"] in ("IMPLEMENTED", "NOT_FOUND")


class TestIndependentRuntimeStates:
    def test_default_runtime_not_verified(self, tmp_path):
        matrix = build_feature_evidence(_mini_project(tmp_path), None)
        jump = _feat(matrix, "jump")
        assert jump["implementation"] == "IMPLEMENTED"
        assert jump["runtime"] == "NOT_VERIFIED"

    def test_honest_gameplay_marks_verified_mechanics_only(self, tmp_path):
        gv = {"gameplay_entered": True, "jump_detected": True, "player_movement_verified": False}
        matrix = build_feature_evidence(_mini_project(tmp_path), gv)
        assert _feat(matrix, "jump")["runtime"] == "VERIFIED"
        assert _feat(matrix, "player_movement")["runtime"] == "NOT_VERIFIED"

    def test_no_runtime_verification_without_gameplay_entered(self, tmp_path):
        gv = {"gameplay_entered": False, "jump_detected": True}
        matrix = build_feature_evidence(_mini_project(tmp_path), gv)
        assert _feat(matrix, "jump")["runtime"] != "VERIFIED"


class TestCaptureFailureNeverErasesStatic:
    def test_environment_failure_keeps_implementation_pass(self, tmp_path):
        gv = {"gameplay_entered": False, "failure_reason_code": "GAME_WINDOW_CAPTURE_FAILED"}
        matrix = build_feature_evidence(_mini_project(tmp_path), gv)
        jump = _feat(matrix, "jump")
        assert jump["implementation"] == "IMPLEMENTED"
        assert jump["runtime"] == "FAILED_ENVIRONMENT"
        assert "does not invalidate static analysis" in jump["runtime_reason"]
        assert matrix["runtime_session"]["environment_failure"] is True

    def test_mandated_statement_present_when_runtime_unconfirmed(self, tmp_path):
        matrix = build_feature_evidence(_mini_project(tmp_path), {"gameplay_entered": False})
        assert "verified statically" in matrix["mandated_statement_en"]
        assert "not for proving implementation" in matrix["mandated_statement_en"]
        assert "تحليلياً" in matrix["mandated_statement_ar"]

    def test_merge_does_not_mutate_static_fields(self, tmp_path):
        static = scan_godot_project(_mini_project(tmp_path))
        before = [(f["feature_id"], f["implementation"], f["implementation_confidence"]) for f in static["features"]]
        merged = merge_runtime_states(static, {"failure_reason_code": "GAME_WINDOW_CAPTURE_FAILED"})
        after = [(f["feature_id"], f["implementation"], f["implementation_confidence"]) for f in merged["features"]]
        assert before == after
