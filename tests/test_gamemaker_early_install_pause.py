"""Tests for GameMaker source-only early soft-pause (no .exe, IDE missing)."""
from __future__ import annotations

from app.runtime_engines.gamemaker import install_gate as gate


def test_exe_present_never_soft_pauses(monkeypatch):
    monkeypatch.setattr(gate, "gamemaker_ide_tools_available", lambda: False)
    paths = [
        "student/game.exe",
        "student/objects/obj_player/Step_0.gml",
        "student/project.yyp",
    ]
    assert gate.should_soft_pause_for_missing_gamemaker_ide(paths) is False


def test_source_only_without_ide_soft_pauses(monkeypatch):
    monkeypatch.setattr(gate, "gamemaker_ide_tools_available", lambda: False)
    paths = [
        "student/project.yyp",
        "student/objects/obj_player/Step_0.gml",
        "student/report.docx",
    ]
    assert gate.should_soft_pause_for_missing_gamemaker_ide(paths) is True


def test_source_only_with_ide_does_not_pause(monkeypatch):
    monkeypatch.setattr(gate, "gamemaker_ide_tools_available", lambda: True)
    paths = ["student/project.yyp", "student/Create_0.gml"]
    assert gate.should_soft_pause_for_missing_gamemaker_ide(paths) is False


def test_build_pause_result_is_success_not_grd001(monkeypatch):
    monkeypatch.setattr(gate, "gamemaker_ide_tools_available", lambda: False)
    result = gate.build_gamemaker_install_pause_result(
        student_info={
            "name": "احمد عبد الملك",
            "path": "uploads/students/x/report.docx",
            "email": "",
            "student_id": "",
        },
        submission_paths=[
            "student/project.yyp",
            "student/Create_0.gml",
            "student/الهدف ب.docx",
        ],
        grading_criteria=[
            {"level": "C.P5", "max_score": 25},
            {"level": "C.P6", "max_score": 25},
        ],
        grading_mode="pro",
    )
    assert result["success"] is True
    assert "error" not in result or not result.get("error")
    assert result["grading_paused"]["paused"] is True
    assert result["gamemaker_install_pause_banner"]["active"] is True
    assert "GameMaker" in result["gamemaker_install_pause_banner"]["title_ar"]
    assert result["grade_level"] == "U"
    assert len(result["criteria_results"]) == 2


def test_example_txt_does_not_count_as_exe():
    """Regression: 'example.txt' must not look like a runnable .exe path."""
    assert gate.has_runnable_gamemaker_or_exe_build(["student/example.txt"]) is False
    assert gate.has_runnable_gamemaker_or_exe_build(["student/game.exe"]) is True
