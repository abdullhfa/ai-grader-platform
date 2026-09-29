"""Game grading policy: runtime first -> source-code fallback -> temp build deleted."""
from __future__ import annotations

from pathlib import Path

from app.game_source_mechanics import analyze_source_mechanics
from app.game_verification_policy import (
    TemporaryGameBuild,
    cleanup_session_temporary_builds,
    prepare_temporary_executable,
    reconcile_game_requirements,
)


def _gv(entered=True, **verified):
    return {
        "gameplay_entered": entered,
        "evidence_package": {
            "results": [{"req_id": k, "verified": v, "reason": "test"} for k, v in verified.items()]
        },
    }


# ---------------------------------------------------------------- source analyzer
def test_gdscript_movement_and_jump_detected(tmp_path: Path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    (tmp_path / "player.gd").write_text(
        "extends CharacterBody2D\n"
        "func _physics_process(delta):\n"
        "    var dir = Input.get_axis('ui_left', 'ui_right')\n"
        "    velocity.x = dir * SPEED\n"
        "    if Input.is_action_just_pressed('jump') and is_on_floor():\n"
        "        velocity.y = JUMP_VELOCITY\n"
        "    move_and_slide()\n",
        encoding="utf-8",
    )
    rep = analyze_source_mechanics(tmp_path)
    assert "player_movement" in rep["detected_ids"]
    assert "player_jump" in rep["detected_ids"]
    ev = rep["mechanics"]["player_jump"]["evidence"][0]
    assert ev["file"].endswith("player.gd") and ev["line"] > 0


def test_gravity_alone_is_not_a_jump(tmp_path: Path):
    (tmp_path / "enemy.gd").write_text("var gravity = 900\nvelocity.y += gravity * delta\n", encoding="utf-8")
    rep = analyze_source_mechanics(tmp_path)
    assert "player_jump" not in rep["detected_ids"]


def test_unity_csharp_and_pygame(tmp_path: Path):
    (tmp_path / "Player.cs").write_text(
        'float h = Input.GetAxis("Horizontal");\n'
        'if (Input.GetButtonDown("Jump")) rb.AddForce(Vector2.up * jumpForce);\n'
        "score += 10;\n",
        encoding="utf-8",
    )
    (tmp_path / "game.py").write_text("if keys[pygame.K_SPACE]:\n    vel_y = -12\nlives -= 1\n", encoding="utf-8")
    rep = analyze_source_mechanics(tmp_path)
    for mid in ("player_movement", "player_jump", "score_system", "lives_system"):
        assert mid in rep["detected_ids"], mid


def test_commented_code_is_ignored(tmp_path: Path):
    (tmp_path / "p.gd").write_text("# Input.is_action_just_pressed('jump')\n", encoding="utf-8")
    assert "player_jump" not in analyze_source_mechanics(tmp_path)["detected_ids"]


# ---------------------------------------------------------------- reconciliation
def test_runtime_verified_needs_no_code_check():
    rep = reconcile_game_requirements(_gv(player_movement=True), {}, required_ids=["player_movement"])
    row = rep["requirements"][0]
    assert row["status"] == "runtime_verified"
    assert row["code_checked"] is False
    assert row["teacher_confirmation_required"] is False


def test_runtime_failure_falls_back_to_code(tmp_path: Path):
    (tmp_path / "p.gd").write_text("if Input.is_action_just_pressed('jump'):\n    velocity.y = -400\n", encoding="utf-8")
    src = analyze_source_mechanics(tmp_path)
    rep = reconcile_game_requirements(
        _gv(player_movement=True, player_jump=False), src,
        required_ids=["player_movement", "player_jump", "score_system"],
    )
    by = {r["req_id"]: r for r in rep["requirements"]}
    assert by["player_movement"]["status"] == "runtime_verified"
    assert by["player_jump"]["status"] == "code_verified_runtime_unconfirmed"
    assert by["player_jump"]["teacher_confirmation_required"] is True
    assert by["player_jump"]["code_evidence"]
    assert by["score_system"]["status"] == "not_verified"
    assert rep["all_requirements_met"] is False


def test_runtime_results_ignored_when_gameplay_not_entered():
    rep = reconcile_game_requirements(_gv(entered=False, player_movement=True), {}, required_ids=["player_movement"])
    assert rep["requirements"][0]["status"] == "not_verified"


# ---------------------------------------------------------------- temp build lifecycle
def test_no_project_means_no_temp_build(tmp_path: Path):
    (tmp_path / "report.docx").write_bytes(b"PK")
    assert prepare_temporary_executable([tmp_path / "report.docx"], tmp_path) is None


def test_temp_build_workspace_always_deleted(tmp_path: Path):
    ws = tmp_path / "ws"
    (ws / "build").mkdir(parents=True)
    exe = ws / "build" / "Game.exe"
    exe.write_bytes(b"MZ")
    b = TemporaryGameBuild("godot", ws, executable=exe)
    assert b.success
    res = b.cleanup()
    assert res["deleted"] is True and not ws.exists()
    assert b.to_dict()["cleanup"]["deleted"] is True


def test_godot_export_uses_isolated_copy(tmp_path: Path, monkeypatch):
    student = tmp_path / "student"
    student.mkdir()
    (student / "project.godot").write_text("[application]\n", encoding="utf-8")
    (student / "player.gd").write_text("extends Node\n", encoding="utf-8")
    seen = {}

    def fake_export(project_root, **_kw):
        seen["root"] = Path(project_root)
        out = Path(project_root) / "build" / "game.exe"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"MZ")
        return {"success": True, "artifact": str(out)}

    from app.runtime_engines.godot import export_runner

    monkeypatch.setattr(export_runner, "run_godot_export", fake_export)
    b = prepare_temporary_executable([student / "project.godot"], student)
    assert b is not None and b.engine == "godot" and b.success
    assert student not in seen["root"].parents and seen["root"] != student
    assert not (student / "build").exists(), "student folder must stay untouched"
    b.cleanup()
    assert not b.workspace.exists()


def test_session_cleanup_removes_registered_dirs(tmp_path: Path):
    class S:
        workspace = tmp_path
        signals = {}

    (tmp_path / "gm_ide_build" / "x").mkdir(parents=True)
    rep = cleanup_session_temporary_builds(S())
    assert rep["deleted_all"] and not (tmp_path / "gm_ide_build").exists()


def test_sandbox_source_only_builds_runs_and_deletes(tmp_path: Path, monkeypatch):
    """No .exe -> temp build -> smoke test -> build deleted -> code fallback."""
    from app import runtime_observation_sandbox as ros
    from app.runtime_engines.godot import export_runner

    student = tmp_path / "student"
    student.mkdir()
    (student / "project.godot").write_text("[application]\n", encoding="utf-8")
    (student / "player.gd").write_text(
        "var d = Input.get_axis('ui_left','ui_right')\nif Input.is_action_just_pressed('jump'):\n    velocity.y = -300\n",
        encoding="utf-8",
    )
    built = {}

    def fake_export(project_root, **_kw):
        out = Path(project_root) / "build" / "game.exe"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"MZ" + b"\0" * 64)
        built["exe"] = out
        return {"success": True, "artifact": str(out)}

    def fake_smoke(path, **_kw):
        built["ran"] = Path(path)
        return {"type": "exe", "artifact": Path(path).name, "attempted": True,
                "smoke_result": "stable_window", "signals": {},
                "gameplay_verification": {
                    "gameplay_entered": True,
                    "evidence_package": {"results": [
                        {"req_id": "player_movement", "verified": True},
                        {"req_id": "player_jump", "verified": False},
                    ]},
                }}

    monkeypatch.setattr(export_runner, "run_godot_export", fake_export)
    monkeypatch.setattr(ros, "smoke_test_windows_exe", fake_smoke)
    monkeypatch.setattr(ros, "detect_unity_build_for_exe", lambda p: {"detected": False})
    paths = [str(p) for p in student.iterdir()]
    obs = ros.observe_runtime_artifacts(paths, enable_smoke_test=True,
                                        required_requirement_ids=["player_movement", "player_jump"])
    assert built["ran"] == built["exe"]
    assert not built["exe"].exists(), "temporary .exe must be deleted after grading"
    assert obs["temporary_build"]["cleanup"]["deleted"] is True
    by = {r["req_id"]: r for r in obs["requirement_verification"]["requirements"]}
    assert by["player_movement"]["status"] == "runtime_verified"
    assert by["player_jump"]["status"] == "code_verified_runtime_unconfirmed"
    assert "GAME REQUIREMENTS" in ros.format_observation_for_grading(obs)
