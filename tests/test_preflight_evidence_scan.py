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


def test_scan_flags_missing_test_plan_and_bug_log():
    paths = ["Student/project.godot", "Student/report.docx"]
    r = scan_relative_paths(paths)
    assert "خطة اختبار (Test Plan)" in r["critical_missing_ar"]
    assert "سجل أخطاء (Bug Log)" in r["critical_missing_ar"]
    assert r["warn_teacher"] is True
    assert r["expected_grade_hint"] == "U"


def test_scan_zip_archive(tmp_path: Path):
    zpath = tmp_path / "sub.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Ali/test_plan.docx", b"x")
        zf.writestr("Ali/bug_log.xlsx", b"x")
        zf.writestr("Ali/project.godot", b"config_version=5")
    r = scan_archive_file(str(zpath))
    keys = {i["key"]: i["present"] for i in r["items"]}
    assert keys["test_plan"] is True
    assert keys["bug_log"] is True
    assert r["warn_teacher"] is False
