"""Tests for fast pre-grade path-only evidence scan."""
import zipfile
from pathlib import Path

from app.preflight_evidence_scan import (
    scan_archive_file,
    scan_relative_paths,
)


def test_scan_finds_gdd_and_project():
    paths = [
        "Student/project.godot",
        "Student/GDD_v1.docx",
        "Student/game.exe",
    ]
    r = scan_relative_paths(paths)
    assert r["engine_detected"] == "godot"
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["gdd"] is True
    assert keys["project"] is True
    assert keys["executable"] is True


def test_scan_flags_missing_test_plan_advisory_only():
    paths = ["Student/project.godot", "Student/report.docx"]
    r = scan_relative_paths(paths)
    assert any("خطة اختبار" in x for x in r["advisory_missing_ar"])
    assert not any("Bug Log" in x or "سجل أخطاء" in x for x in r["advisory_missing_ar"])
    assert r["warn_teacher"] is True
    # No runnable build in paths — advisory P?, not forced U for missing test/bug filenames
    assert r["expected_grade_hint"] == "P?"


def test_gamemaker_core_deliverables_not_u_without_separate_test_files():
    """GameMaker + nested build + GDD + Word — must not show U for missing test/bug filenames."""
    paths = [
        "واجب/(.exe)بعد التعديل.zip",
        "واجب/(.exe)قبل التعديل.zip",
        "واجب/بعد التعديل.yyp",
        "Student/تصميم لعبة الذاكرة.pptx",
        "Student/واجب الالعاب.docx",
        "Student/Memory_Game_Design_Document_COMPLETE.docx",
    ]
    r = scan_relative_paths(paths)
    assert r["expected_grade_hint"] in ("P", "P+")
    assert r["warn_teacher"] is True
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["project"] is True
    assert keys["executable"] is True
    assert keys["gdd"] is True


def test_scan_detects_scratch_project_as_runnable_game():
    """Regression: a Scratch .sb3 is a self-contained runnable game and must register
    as both project + executable-equivalent (was previously ✗ → wrong U)."""
    paths = [
        "U9 PART B+C/Scratch Project2.sb3",
        "U9 PART B+C/Report.docx",
    ]
    r = scan_relative_paths(paths)
    assert r["engine_detected"] == "scratch"
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["project"] is True
    assert keys["executable"] is True


def test_scan_scratch_zip_not_u_for_missing_exe(tmp_path: Path):
    """A ZIP with .sb3 + Test Plan + Bug Log must not be U just because no .exe exists."""
    zpath = tmp_path / "scratch_sub.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Lara/Scratch Project2.sb3", b"PK-scratch")
        zf.writestr("Lara/test_plan.docx", b"x")
        zf.writestr("Lara/bug_log.xlsx", b"x")
        zf.writestr("Lara/GDD_game_design.docx", b"x")
    r = scan_archive_file(str(zpath))
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["project"] is True
    assert keys["executable"] is True
    assert r["warn_teacher"] is False
    assert r["expected_grade_hint"] != "U"


def test_scan_gamemaker_data_win_is_runnable():
    paths = ["Game/data.win", "Game/options.ini", "Game/report.pdf"]
    r = scan_relative_paths(paths)
    assert r["engine_detected"] == "gamemaker"
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["project"] is True
    assert keys["executable"] is True


def test_scan_nested_exe_zip_counts_as_build():
    """Regression: «(.exe)بعد التعديل.zip» inside RAR must register as build."""
    paths = [
        "واجب/(.exe)بعد التعديل.zip",
        "واجب/(.exe)قبل التعديل.zip",
        "واجب/بعد التعديل.yyp",
        "واجب/objects/obj_player/obj_player.yy",
    ]
    r = scan_relative_paths(paths)
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["project"] is True
    assert keys["executable"] is True


def test_scan_arabic_gdd_pptx_filename():
    """«تصميم لعبة الذاكرة.pptx» should match GDD by Arabic filename."""
    paths = ["Student/تصميم لعبة الذاكرة.pptx", "Student/report.docx"]
    r = scan_relative_paths(paths)
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["gdd"] is True


def test_scan_zip_archive(tmp_path: Path):
    zpath = tmp_path / "sub.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Ali/test_plan.docx", b"x")
        zf.writestr("Ali/bug_log.xlsx", b"x")
        zf.writestr("Ali/project.godot", b"config_version=5")
    r = scan_archive_file(str(zpath))
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["test_plan"] is True
    assert "bug_log" not in keys
    assert r["expected_grade_hint"] == "P?"
