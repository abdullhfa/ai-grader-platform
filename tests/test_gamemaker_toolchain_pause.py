"""GameMaker dependency pause/resume preflight and V1/V2 governance."""
from __future__ import annotations

from pathlib import Path

from app.runtime_engines.gamemaker.toolchain import (
    discover_gamemaker_toolchain,
    preflight_gamemaker_runtime_dependency,
)


def _isolate_gamemaker_search(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "programdata"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "programfiles"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "programfiles-x86"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("PATH", "")
    for name in (
        "AI_GRADER_GAMEMAKER_IDE",
        "AI_GRADER_GAMEMAKER_IGOR",
        "AI_GRADER_GAMEMAKER_RUNTIME_ROOT",
        "AI_GRADER_GAMEMAKER_USER_FOLDER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.toolchain._registry_ide_candidates",
        lambda: [],
    )


def test_source_project_pauses_when_gamemaker_is_missing(tmp_path: Path, monkeypatch):
    _isolate_gamemaker_search(monkeypatch, tmp_path)
    project = tmp_path / "student" / "V2"
    project.mkdir(parents=True)
    yyp = project / "Game.yyp"
    yyp.write_text("{}", encoding="utf-8")

    result = preflight_gamemaker_runtime_dependency(
        [{"name": "Student", "path": str(yyp), "submission_paths": [str(yyp)]}]
    )

    assert result["gamemaker_detected"] is True
    assert result["pause_required"] is True
    assert result["pause_reason"] == "gamemaker_not_installed"


def test_supplied_runnable_exe_does_not_require_installed_ide(tmp_path: Path, monkeypatch):
    _isolate_gamemaker_search(monkeypatch, tmp_path)
    build = tmp_path / "student" / "V2"
    build.mkdir(parents=True)
    exe = build / "Game.exe"
    exe.write_bytes(b"MZ")
    (build / "data.win").write_bytes(b"runtime")

    result = preflight_gamemaker_runtime_dependency(
        [{"name": "Student", "path": str(exe), "submission_paths": [str(exe), str(build / "data.win")]}]
    )

    assert result["gamemaker_detected"] is True
    assert result["pause_required"] is False
    assert result["projects"][0]["runnable_supplied"] is True


def test_discovery_is_ready_with_igor_runtime_and_login(tmp_path: Path, monkeypatch):
    _isolate_gamemaker_search(monkeypatch, tmp_path)
    runtime = tmp_path / "runtime-2024.11"
    igor = runtime / "bin" / "igor" / "windows" / "x64" / "Igor.exe"
    igor.parent.mkdir(parents=True)
    igor.write_bytes(b"MZ")
    user = tmp_path / "gm-user"
    user.mkdir()
    (user / "licence.plist").write_text("ready", encoding="utf-8")
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_IGOR", str(igor))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_USER_FOLDER", str(user))

    result = discover_gamemaker_toolchain()

    assert result.installed is True
    assert result.ready is True
    assert result.reason == "ready"


def test_paused_checkpoint_is_not_auto_resumed(tmp_path: Path, monkeypatch):
    from app import batch_checkpoint

    monkeypatch.setattr(batch_checkpoint, "_CHECKPOINT_DIR", tmp_path)
    batch_checkpoint.save_batch_checkpoint(
        7,
        {
            "batch_id": 7,
            "assignment_id": 3,
            "stage": "grading",
            "paused": True,
            "pause_kind": "gamemaker_dependency",
        },
    )

    assert batch_checkpoint.load_batch_checkpoint(7)["paused"] is True
    assert batch_checkpoint.list_resumable_checkpoints() == []


def test_v1_without_v2_blocks_gamemaker_improvement_criteria(tmp_path: Path):
    from app.artifact_inventory import build_artifact_inventory
    from app.criteria_result_finalizer import finalize_grading_criteria_results

    v1 = tmp_path / "V1"
    v1.mkdir()
    yyp = v1 / "Game.yyp"
    yyp.write_text("{}", encoding="utf-8")
    gr = {
        "criteria_results": [
            {"criteria_level": "8/C.M3", "achieved": True, "score": 100, "feedback": "تحسين كامل"},
            {"criteria_level": "8/BC.D2", "achieved": True, "score": 100, "feedback": "تقييم النسخة"},
        ]
    }
    inventory = build_artifact_inventory(
        main_document_path=None,
        submission_paths=[str(yyp)],
        skip_runtime_observation=True,
        skip_heavy_enrichment=True,
        skip_l2_l3_corroborative=True,
        skip_governance_graphs=True,
    )

    finalize_grading_criteria_results(gr, artifact_inventory=inventory)

    assert all(row["achieved"] is False for row in gr["criteria_results"])
    assert all(row.get("version_gate_block") for row in gr["criteria_results"])

