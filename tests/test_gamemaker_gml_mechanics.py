"""Determinism + evidence tests for the GameMaker GML mechanics analyzer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.gameplay_semantic_verification import assess_gameplay_semantics
from app.mechanics_verifier import verify_mechanics
from app.requirement_checklist import build_requirement_checklist
from app.requirement_extractor import RequirementExtractor
from app.runtime_criterion_mapping import evaluate_operational_support
from app.runtime_engines.gamemaker.gml_mechanics import analyze_gml_mechanics


@pytest.fixture()
def gm_project(tmp_path: Path) -> Path:
    """Minimal GameMaker project: movement + timer + lives + win/lose."""
    obj = tmp_path / "objects" / "obj_player"
    obj.mkdir(parents=True)
    (obj / "Step_0.gml").write_text(
        "if (keyboard_check(vk_right)) x += 4;\n"
        "if (keyboard_check(vk_left)) x -= 4;\n"
        "if (place_meeting(x, y, obj_enemy)) { lives -= 1; }\n"
        "if (lives <= 0) { global.state = \"game_over\"; game_restart(); }\n",
        encoding="utf-8",
    )
    ctrl = tmp_path / "objects" / "obj_ctrl"
    ctrl.mkdir(parents=True)
    (ctrl / "Alarm_0.gml").write_text(
        "timer -= 1;\nalarm[0] = room_speed;\nif (timer <= 0) room_goto(rm_win);\n",
        encoding="utf-8",
    )
    (ctrl / "Draw_0.gml").write_text(
        'draw_text(10, 10, "Score: " + string(score));\n'
        'draw_text(10, 30, "Lives: " + string(lives));\n'
        'draw_text(10, 50, "Time: " + string(timer));\n',
        encoding="utf-8",
    )
    for room in ("rm_level1", "rm_win"):
        (tmp_path / "rooms" / room).mkdir(parents=True)
    return tmp_path


def test_detects_required_mechanics_with_evidence(gm_project: Path) -> None:
    result = analyze_gml_mechanics(gm_project)
    detected = set(result["detected_ids"])
    assert {"player_movement", "timer_system", "lives_system",
            "score_system", "collision", "lose_condition"} <= detected
    for mech_id in ("timer_system", "lives_system"):
        evidence = result["mechanics"][mech_id]["evidence"]
        assert evidence, f"{mech_id} must carry evidence"
        assert all(e["file"] and "snippet" in e for e in evidence)


def test_analyzer_is_deterministic(gm_project: Path) -> None:
    outs = {
        json.dumps(analyze_gml_mechanics(gm_project), sort_keys=True)
        for _ in range(3)
    }
    assert len(outs) == 1


def test_static_evidence_flows_to_semantics_and_criteria(gm_project: Path) -> None:
    static = analyze_gml_mechanics(gm_project)
    obs = {
        "runtime_observed": True,
        "static_mechanics": static,
        "artifact_analyses": [{"type": "exe", "smoke_result": "stable_window"}],
        "runtime_signal_graph": {"signals": {"crash": "none"}},
    }
    sem = assess_gameplay_semantics(obs)
    assert sem["timer_system_detected"] is True
    assert sem["lives_or_health_detected"] is True

    mech = verify_mechanics(obs)
    assert mech["timer_system_detected"] is True
    assert mech["lives_or_health_detected"] is True
    assert mech["player_movement_detected"] is True

    runs = {
        json.dumps(evaluate_operational_support(obs, {}), sort_keys=True)
        for _ in range(3)
    }
    assert len(runs) == 1, "criterion support must be identical across runs"
    sup = json.loads(next(iter(runs)))
    assert sup["C.P5"]["support_score"] > 0
    assert any("دليل ثابت" in r for r in sup["C.P6"]["reasons_ar"])


def test_arabic_brief_extracts_timer_and_lives_requirements() -> None:
    brief = "المطلوب: إضافة وقت محدد (مؤقت) وإضافة أرواح للاعب مع نظام نقاط"
    checklist = build_requirement_checklist(student_text=brief)
    assert "timer_system" in checklist["requirement_ids"]
    assert "lives_system" in checklist["requirement_ids"]

    plan = RequirementExtractor().extract(engine="gamemaker", student_text=brief)
    ids = plan.requirement_ids()
    assert "timer_system" in ids
    assert "lives_system" in ids
    movement = next(r for r in plan.requirements if r.req_id == "player_movement")
    keys = [a.key for a in movement.input_sequence]
    assert "right" in keys and "left" in keys, "GameMaker plan must send arrow keys"


def test_empty_project_detects_nothing(tmp_path: Path) -> None:
    result = analyze_gml_mechanics(tmp_path)
    assert result["detected_ids"] == []
    assert result["gml_files_scanned"] == 0


def _make_frames(tmp_path: Path) -> list:
    """Two visibly different frames — a live game that keeps rendering."""
    from PIL import Image

    shots = []
    for idx, base in enumerate((40, 200)):
        img = Image.new("RGB", (64, 64))
        img.putdata([((base + x) % 255, (x * 3) % 255, base) for x in range(64 * 64)])
        p = tmp_path / f"frame_{idx}.png"
        img.save(p)
        shots.append(
            {"status": "captured", "path": str(p), "label": "launch" if idx == 0 else "mid_runtime"}
        )
    return shots


def _observation(gm_project: Path, tmp_path: Path) -> dict:
    static = analyze_gml_mechanics(gm_project)
    return {
        "status": "completed",
        "runtime_observed": True,
        "runtime_verified": True,
        "runtime_duration_seconds": 30.0,
        "runtime_screenshots": _make_frames(tmp_path),
        "artifact_analyses": [
            {
                "type": "exe",
                "artifact": "game.exe",
                "smoke_result": "stable_window",
                "signals": {"crash": "none", "runtime_launch_attempted": True},
            }
        ],
        "runtime_signal_graph": {
            "signals": {
                "crash": "none",
                "runtime_launch_attempted": True,
                "interaction_input_sent": "yes",
            }
        },
        "gameplay_verification": {
            "gameplay_entered": False,
            "l4_level": "L3",
            "mechanics_verified_count": 0,
        },
        "static_mechanics": static,
    }


def test_source_only_submission_attempts_build_and_records_static(
    gm_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-EXE GameMaker submission: auto-build attempted; static evidence kept."""
    from app import runtime_observation_sandbox as ros
    from app.runtime_engines.gamemaker import ide_builder

    # Do not block the suite waiting for a real GameMaker install.
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS", "0")

    calls = {}

    def fake_build(yyp, workspace, timeout_seconds=None):
        calls["yyp"] = str(yyp)
        return {
            "attempted": True,
            "success": False,
            "executable": None,
            "reason": "gamemaker_runtime_not_installed",
            "reason_ar": "لم يُعثر على GameMaker على جهاز التصحيح.",
        }

    monkeypatch.setattr(ide_builder, "build_from_source", fake_build)

    yyp = gm_project / "CheeseTest.yyp"
    yyp.write_text('{"resources": []}', encoding="utf-8")
    paths = [str(p) for p in sorted(gm_project.rglob("*")) if p.is_file()]

    obs = ros.observe_runtime_artifacts(paths, enable_smoke_test=True)
    assert obs["status"] == "no_artifacts"
    build = obs.get("gamemaker_ide_build") or {}
    assert build.get("attempted") is True, "auto-build must be attempted for source-only"
    assert calls["yyp"].endswith(".yyp")
    static = obs.get("static_mechanics") or {}
    assert "timer_system" in (static.get("detected_ids") or [])
    assert "lives_system" in (static.get("detected_ids") or [])


def test_grading_pauses_when_gamemaker_missing(gm_project: Path) -> None:
    """Source-only project + GameMaker not installed → PAUSED with Arabic message."""
    from app.runtime_evidence_gate import apply_runtime_evidence_gate

    static = analyze_gml_mechanics(gm_project)
    paths = [str(p) for p in sorted(gm_project.rglob("*.gml"))] + [
        str(gm_project / "project.yyp")
    ]
    obs = {
        "status": "no_artifacts",
        "static_mechanics": static,
        "gamemaker_ide_build": {
            "attempted": False,
            "success": False,
            "reason": "gamemaker_runtime_not_installed",
        },
    }
    inv = {
        "runtime_observation_report": obs,
        "static_mechanics": static,
        "intake_relative_paths": paths,
        "submission_paths": paths,
        "runtime_artifacts": {"gamemaker_detected": True},
    }
    gr = {
        "criteria_results": [
            {"criteria_level": "C.P5", "achieved": False, "score": 35, "awardable": False}
        ],
        "grading_mode": "deep",
        "intake_relative_paths": paths,
        "submission_paths": paths,
    }
    report = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert report["runtime_status"] == "PAUSED_GAMEMAKER_MISSING"
    paused = gr.get("grading_paused") or {}
    assert paused.get("paused") is True
    assert "GameMaker" in str(paused.get("message_ar"))


def test_gameplay_video_counts_as_evidence(gm_project: Path) -> None:
    """A gameplay video in the submission satisfies the evidence gate path."""
    from app.pro_engine_gameplay_governance import assess_playtest_evidence

    paths = ["game/التصميم.yyp", "game/obj/Step_0.gml", "لعبه.webm"]
    inv = {
        "runtime_observation_report": {"status": "no_artifacts"},
        "runtime_artifacts": {"gamemaker_detected": True},
        "intake_relative_paths": paths,
    }
    a = assess_playtest_evidence(inv, submission_paths=paths)
    assert a["playtest_paths"]["gameplay_video_documented"] is True
    assert a["any_path_satisfied"] is True


def test_ide_builder_reports_missing_tools_gracefully(tmp_path: Path) -> None:
    from app.runtime_engines.gamemaker.ide_builder import build_from_source

    yyp = tmp_path / "p.yyp"
    yyp.write_text("{}", encoding="utf-8")
    result = build_from_source(yyp, tmp_path)
    assert result["success"] is False
    assert result["reason"] in ("windows_only", "gamemaker_runtime_not_installed", "auto_build_disabled")
    assert result["reason_ar"]


def test_no_false_freeze_when_frames_differ(gm_project: Path, tmp_path: Path) -> None:
    """Distinct captured frames must never be classified as a freeze."""
    from app.runtime.validation_engine import validate_runtime_observation

    obs = _observation(gm_project, tmp_path)
    rv = validate_runtime_observation(obs)
    assert rv["freeze_analysis"]["freeze_suspected"] is False
    assert rv["functional_smoke"]["functional_smoke_pass"] is True


def test_runtime_gate_opens_with_static_corroboration(gm_project: Path, tmp_path: Path) -> None:
    """Smoke PASS + code-proven mechanics must open the runtime gate deterministically."""
    from app.pro_engine_gameplay_governance import assess_playtest_evidence
    from app.runtime.validation_engine import validate_runtime_observation
    from app.runtime_evidence_gate import apply_runtime_evidence_gate

    obs = _observation(gm_project, tmp_path)
    rv = validate_runtime_observation(obs)
    inv = {
        "runtime_observation_report": obs,
        "runtime_validation": rv,
        "static_mechanics": obs["static_mechanics"],
        "intake_relative_paths": ["game.exe", "project.yyp", "obj/Step_0.gml", "تقرير.docx"],
        "runtime_artifacts": {"gamemaker_detected": True},
        "has_executable_artifacts": True,
        "executable_artifacts": {"files": ["game.exe"]},
    }

    assessment = assess_playtest_evidence(inv, submission_paths=inv["intake_relative_paths"])
    assert assessment["static_corroborated_runtime"] is True
    assert assessment["any_path_satisfied"] is True
    assert assessment["core_mechanics_observed"] >= 2

    def make_result() -> dict:
        rows = [
            {"criteria_level": lvl, "achieved": True, "score": 75, "awardable": True}
            for lvl in ("B.P3", "B.P4", "C.P5", "C.P6", "B.M2", "C.M3")
        ]
        return {
            "criteria_results": rows,
            "grading_mode": "deep",
            "intake_relative_paths": inv["intake_relative_paths"],
        }

    outcomes = set()
    for _ in range(3):
        gr = make_result()
        report = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
        outcomes.add(
            json.dumps(
                {
                    "status": report["runtime_status"],
                    "grade": gr.get("grade_level"),
                    "blocked": [
                        r["criteria_level"]
                        for r in gr["criteria_results"]
                        if r.get("runtime_gate_block")
                    ],
                },
                sort_keys=True,
            )
        )
    assert len(outcomes) == 1, "gate outcome must be identical across runs"
    result = json.loads(next(iter(outcomes)))
    assert result["status"] == "PASS"
    assert result["blocked"] == []
    assert result["grade"] != "U"
