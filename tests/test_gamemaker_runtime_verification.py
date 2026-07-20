"""Tests for PRO GameMaker runtime verification."""
import json
from pathlib import Path

from app.grading_mode_policy import deep_grading_flags, fast_grading_flags
from app.runtime_engines.gamemaker.object_inspection import inspect_gamemaker_objects
from app.runtime_engines.gamemaker.project_probe import (
    assess_gamemaker_exe_launch,
    materialize_gamemaker_runtime_assets,
    probe_gamemaker_layout,
    resolve_gamemaker_runtime_cwd,
)
from app.runtime_observation_sandbox import smoke_test_windows_exe
from app.runtime_engines.gamemaker.runtime_verification import _try_ide_build, run_build_pipeline
from app.runtime_engines.registry import resolve_engine


def test_pro_only_gamemaker_runtime_flag():
    assert fast_grading_flags("fast")["enable_gamemaker_runtime_verification"] is False
    assert deep_grading_flags("deep")["enable_gamemaker_runtime_verification"] is True


def test_gamemaker_engine_resolves(tmp_path: Path):
    (tmp_path / "Demo.yyp").write_text(
        '{"resourceType":"GMProject","resources":[{"id":{"name":"obj_player"},"resourceType":"GMObject"}]}',
        encoding="utf-8",
    )
    engine = resolve_engine(tmp_path)
    assert engine is not None
    assert engine.engine_id == "gamemaker"


def test_object_inspection_finds_objects_events(tmp_path: Path):
    (tmp_path / "Demo.yyp").write_text(
        '{"resourceType":"GMProject","resources":[{"id":{"name":"obj_player"},"resourceType":"GMObject"},{"id":{"name":"rm_main"},"resourceType":"GMRoom"}]}',
        encoding="utf-8",
    )
    obj = tmp_path / "objects" / "obj_player"
    obj.mkdir(parents=True)
    (obj / "Create_0.gml").write_text("x = 0;\n", encoding="utf-8")
    (tmp_path / "rooms" / "rm_main").mkdir(parents=True)

    layout = probe_gamemaker_layout(tmp_path / "Demo.yyp")
    inspection = inspect_gamemaker_objects(layout)
    assert inspection["inspection_ok"] is True
    assert inspection["summary"]["objects"] >= 1
    assert inspection["summary"]["events"] >= 1
    assert inspection["summary"]["rooms"] >= 1


def test_build_pipeline_yyp_ready(tmp_path: Path):
    yyp = tmp_path / "Demo.yyp"
    yyp.write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")
    layout = probe_gamemaker_layout(yyp)
    pipeline = run_build_pipeline(layout, workspace=tmp_path / "ws", timeout_seconds=5)
    assert pipeline["yyp_ready"] is True


def test_ide_build_disabled_without_explicit_flag(tmp_path: Path, monkeypatch):
    yyp = tmp_path / "Demo.yyp"
    yyp.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_IDE", r"C:\GameMaker\GameMaker.exe")
    monkeypatch.delenv("AI_GRADER_GAMEMAKER_IDE_BUILD", raising=False)
    out = _try_ide_build(yyp, tmp_path / "ws", timeout_seconds=5)
    assert out["attempted"] is False
    assert out["reason"] == "gamemaker_ide_build_disabled"


def test_resolve_runtime_cwd_finds_parent_data_win(tmp_path: Path):
    v1 = tmp_path / "V1"
    project = v1 / "Project"
    project.mkdir(parents=True)
    (v1 / "data.win").write_bytes(b"win")
    exe = project / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    assert resolve_gamemaker_runtime_cwd(exe) == v1.resolve()


def test_assess_blocks_launch_without_data_win(tmp_path: Path):
    v1 = tmp_path / "V1" / "Project"
    v1.mkdir(parents=True)
    exe = v1 / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (v1 / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    (tmp_path / "Demo.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    assessment = assess_gamemaker_exe_launch(exe, search_root=tmp_path)
    assert assessment["is_gamemaker"] is True
    assert assessment["launch_allowed"] is False
    assert assessment["skip_reason"] == "missing_data_win"
    json.dumps(assessment)

    smoke = smoke_test_windows_exe(exe, session_ctx={"submission_root": str(tmp_path)})
    assert smoke["attempted"] is False
    assert smoke["smoke_result"] == "skipped_missing_data_win"
    assert smoke["verification_outcome"] == "NOT_VERIFIED"
    assert smoke["academic_outcome"] == "PENDING"


def test_smoke_early_returns_always_have_governed_result(tmp_path: Path):
    missing = smoke_test_windows_exe(tmp_path / "missing.exe")
    non_exe = tmp_path / "readme.txt"
    non_exe.write_text("x", encoding="utf-8")
    invalid = smoke_test_windows_exe(non_exe)
    for result, expected in ((missing, "skipped_missing_executable"), (invalid, "skipped_not_executable")):
        assert result["smoke_result"] == expected
        assert result["verification_outcome"] == "NOT_VERIFIED"
        assert result["academic_outcome"] == "PENDING"


def test_materialize_data_win_from_upload_zip(tmp_path: Path):
    upload_dir = tmp_path / "batch_1_upload"
    upload_dir.mkdir()
    export = tmp_path / "student" / "V1"
    export.mkdir(parents=True)
    exe = export / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "student" / "CheeseChase.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    import zipfile

    zpath = upload_dir / "student.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("student/V1/data.win", b"win-bytes")
        zf.writestr("student/V1/options.ini", b"[Windows]\n")
        zf.writestr("student/V1/CheeseChase.exe", b"MZ")

    out = materialize_gamemaker_runtime_assets(exe, search_root=tmp_path / "student")
    assert out["materialized"] is True
    assert (export / "data.win").is_file()


def test_assess_finds_data_win_in_submission_tree(tmp_path: Path):
    export = tmp_path / "التصميم" / "V1"
    export.mkdir(parents=True)
    exe = export / "CheeseChase.exe"
    exe.write_bytes(b"MZ")
    (export / "options.ini").write_text("[Windows]\n", encoding="utf-8")
    assets = tmp_path / "bin"
    assets.mkdir()
    (assets / "data.win").write_bytes(b"win")
    (tmp_path / "CheeseChase.yyp").write_text('{"resourceType":"GMProject","resources":[]}', encoding="utf-8")

    assessment = assess_gamemaker_exe_launch(exe, search_root=tmp_path)
    assert assessment["launch_allowed"] is True
    assert assessment["runtime_cwd"] == str(assets.resolve())
    json.dumps(assessment)
