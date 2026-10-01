"""Batch 3a: "Cannot Run != Not Achieved".

dependency missing → PAUSED → blocker recorded → no final grade
(never: dependency missing → static analysis → COMPLETED)
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.runtime_engines.godot.engine as godot_engine
import app.runtime_engines.unity.engine as unity_engine
from app.assessment_state import (
    MISSING_EVIDENCE,
    NOT_ACHIEVED_BY_RUNTIME,
    NOT_VERIFIED_BLOCKED,
    VERIFIED_BY_RUNTIME,
    compute_assessment_state,
)
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.runtime_engines import dependencies as deps
from app.runtime_engines.base import RuntimeSession, SessionStatus, cleanup_temp_artifacts
from app.runtime_engines.scratch import runtime_verification as scratch_rv
from app.runtime_engines.scratch.engine import ScratchRuntimeEngine


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _launcher_available(monkeypatch):
    """Default: the host can launch Windows exes; launcher tests override this."""
    monkeypatch.setattr(deps, "can_launch_windows_exe", lambda: True)


def _session(engine: str, root: Path) -> RuntimeSession:
    return RuntimeSession.create(engine, "stu", root)


def _unity_project(root: Path) -> Path:
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    (root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.1f1\n")
    return root


def _blocker_codes(session: RuntimeSession):
    return [b.code for b in session.blockers]


# ── Unity ────────────────────────────────────────────────────────────────────
def test_unity_source_without_editor_pauses_not_static_completed(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: None)
    s = _session("unity", proj)
    eng = unity_engine.UnityRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.UNITY_EDITOR_MISSING]
    assert "Unity Editor is required but not installed" in s.blockers[0].detail
    assert s.signals.get("runtime_method") != "unity_static_only"
    assert "unity_source_without_executable" not in s.errors


def test_unity_auto_build_disabled_pauses(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setenv("AI_GRADER_UNITY_AUTO_BUILD", "0")
    s = _session("unity", proj)
    eng = unity_engine.UnityRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.UNITY_AUTO_BUILD_DISABLED]


def test_unity_temp_build_is_registered_and_deleted(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    fake_editor = tmp_path / "Unity"
    fake_editor.write_text("x")
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: fake_editor)

    def fake_build(cfg):
        cfg.output_exe.parent.mkdir(parents=True, exist_ok=True)
        cfg.output_exe.write_bytes(b"MZ")
        return {"success": True, "artifact": str(cfg.output_exe)}

    monkeypatch.setattr(unity_engine, "run_unity_build", fake_build)

    def fake_play(session, cfg):
        raise RuntimeError("play stub")  # play itself is not under test here

    monkeypatch.setattr(unity_engine, "run_unity_play_session", fake_play)
    s = _session("unity", proj)
    eng = unity_engine.UnityRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    built = Path(s.signals["executable"])
    assert built.is_file() and s.temp_artifacts
    removed = cleanup_temp_artifacts(s)
    assert removed and not built.exists()
    assert not s.temp_artifacts
    # evidence (session logs directory) is kept
    assert s.artifact_store.logs.exists()


def test_unity_license_fault_is_env_fault_pause(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: tmp_path / "Unity")
    monkeypatch.setattr(
        unity_engine,
        "run_unity_build",
        lambda cfg: {"success": False, "error": "No valid Unity license found"},
    )
    s = _session("unity", proj)
    eng = unity_engine.UnityRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert s.blockers[0].kind == "ENV_FAULT"


# ── Godot ────────────────────────────────────────────────────────────────────
def _godot_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.godot").write_text("config_version=5\n")
    return root


def test_godot_source_without_binary_pauses(tmp_path, monkeypatch):
    proj = _godot_project(tmp_path / "game")
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: None)
    s = _session("godot", proj)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.GODOT_BINARY_MISSING]
    assert s.signals.get("runtime_method") != "godot_static_analysis"


def test_godot_pck_without_binary_pauses(tmp_path, monkeypatch):
    root = tmp_path / "game"
    root.mkdir()
    (root / "game.pck").write_bytes(b"GDPC")
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: None)
    s = _session("godot", root)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.GODOT_BINARY_MISSING]


def test_godot_temp_export_is_deleted_but_preexisting_build_kept(tmp_path, monkeypatch):
    proj = _godot_project(tmp_path / "game")
    (proj / "build").mkdir()
    (proj / "build" / "student_notes.txt").write_text("keep")
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: tmp_path / "godot")

    def fake_export(project_root, timeout_seconds=60):
        exe = Path(project_root) / "build" / "Game.exe"
        exe.write_bytes(b"MZ")
        exe.with_suffix(".pck").write_bytes(b"GDPC")
        return {"success": True, "artifact": str(exe)}

    monkeypatch.setattr(godot_engine, "run_godot_export", fake_export)
    monkeypatch.setattr(
        "app.runtime_observation_sandbox.smoke_test_windows_exe",
        lambda *a, **k: {"attempted": False, "smoke_result": "launch_ok", "runtime_screenshots": []},
    )
    s = _session("godot", proj)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert (proj / "build" / "Game.exe").is_file()
    cleanup_temp_artifacts(s)
    assert not (proj / "build" / "Game.exe").exists()
    assert not (proj / "build" / "Game.pck").exists()
    assert (proj / "build" / "student_notes.txt").read_text() == "keep"


# ── Scratch ──────────────────────────────────────────────────────────────────
def _sb3(path: Path) -> Path:
    project = {"targets": [{"isStage": True, "name": "Stage", "blocks": {}, "variables": {}}], "meta": {}}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("project.json", json.dumps(project))
    return path


def test_scratch_without_vm_pauses_in_runtime_mode(tmp_path, monkeypatch):
    sb3 = _sb3(tmp_path / "game.sb3")
    monkeypatch.setattr(
        scratch_rv,
        "run_scratch_vm",
        lambda *a, **k: {"success": False, "method": "static_graph_only", "error": "scratch_vm_unavailable"},
    )
    s = _session("scratch", tmp_path)
    s.signals["enable_scratch_runtime_verification"] = True
    eng = ScratchRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.NODE_MISSING]
    assert s.blockers[0].resolvable_by == "install"


# ── orchestrator: PAUSED flows out and temp files are always cleaned ─────────
def test_orchestrator_reports_paused_and_cleans_up(tmp_path, monkeypatch):
    import app.runtime.orchestrator as orch

    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: None)
    monkeypatch.setattr(orch, "is_l4_sandbox_permitted", lambda *a, **k: True)
    result = orch.run_runtime_session("stu", proj, timeout_seconds=5)
    assert result["status"] == "paused"
    assert result["blockers"][0]["code"] == deps.UNITY_EDITOR_MISSING


# ── pure state function ──────────────────────────────────────────────────────
def _row(level, *, achieved=False, runtime=False, block=False):
    return {
        "criteria_level": level,
        "achieved": achieved,
        "awardable": achieved,
        "runtime_l4_verified": runtime,
        "runtime_gate_block": block,
    }


def _result(rows, *, blockers=None, status="completed", paths=("game.exe", "Test plan.docx"), **extra):
    report = {"status": status}
    if status in ("completed", "partial", "failed", "crashed", "timeout"):
        report["runtime_observed"] = True  # a real launch happened (static reports carry no such evidence)
    if blockers:
        report["runtime_blockers"] = blockers
    return {
        "criteria_results": rows,
        "artifact_inventory": {"runtime_observation_report": report},
        "submission_paths": list(paths),
        **extra,
    }


DEP = {"code": "unity_editor_missing", "kind": "MISSING_DEPENDENCY", "detail": "Unity Editor", "resolvable_by": "install"}


def test_blocked_dependency_is_paused_and_never_not_achieved():
    rows = [_row("8/C.P5", block=True), _row("8/C.P6", block=True), _row("8/C.M3", block=True), _row("8/BC.D3")]
    st = compute_assessment_state(_result(rows, blockers=[DEP], status="paused"))
    assert st["state"] == "PAUSED" and st["resume_from"] == "runtime"
    assert set(st["decided"].values()) == {NOT_VERIFIED_BLOCKED}
    assert NOT_ACHIEVED_BY_RUNTIME not in st["decided"].values()
    assert st["final_grade_allowed"] is False


def test_ran_and_failed_is_a_real_negative_and_can_be_final():
    rows = [_row("8/C.P5", achieved=True, runtime=True), _row("8/C.P6", block=True)]
    st = compute_assessment_state(_result(rows))
    assert st["decided"]["P5"] == VERIFIED_BY_RUNTIME
    assert st["decided"]["P6"] == NOT_ACHIEVED_BY_RUNTIME
    assert st["state"] == "FINAL" and st["final_grade_allowed"] is True


def test_missing_test_document_is_missing_evidence_paused_for_upload():
    rows = [_row("8/C.P6", block=True)]
    st = compute_assessment_state(_result(rows, paths=("game.exe",)))
    assert st["decided"]["P6"] == MISSING_EVIDENCE
    assert st["state"] == "PAUSED" and st["resume_from"] == "extracting"


def test_gate_error_is_provisional_not_final():
    rows = [_row("8/C.M3", block=True)]
    st = compute_assessment_state(
        _result(rows, runtime_gate_error={"error": "boom"})
    )
    assert st["state"] == "PROVISIONAL" and st["final_grade_allowed"] is False


def test_grace_disabled_by_default_paused_never_expires(monkeypatch):
    monkeypatch.delenv("EVIDENCE_GRACE_DAYS", raising=False)
    rows = [_row("8/C.P6", block=True)]
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    res = _result(rows, paths=("game.exe",), assessment_state={"paused_since": old})
    assert compute_assessment_state(res)["state"] == "PAUSED"


def test_grace_expires_missing_upload_but_never_a_platform_fault(monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRACE_DAYS", "14")
    old = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    missing = _result([_row("8/C.P6", block=True)], paths=("game.exe",), assessment_state={"paused_since": old})
    assert compute_assessment_state(missing)["state"] == "FINAL"
    platform = _result(
        [_row("8/C.P5", block=True)], blockers=[DEP], status="paused", assessment_state={"paused_since": old}
    )
    assert compute_assessment_state(platform)["state"] == "PAUSED"


def test_state_is_idempotent_and_fingerprint_changes_when_blocker_clears():
    rows = [_row("8/C.P5", block=True)]
    paused = _result(rows, blockers=[DEP], status="paused")
    a, b = compute_assessment_state(paused), compute_assessment_state(paused)
    assert a["evidence_fingerprint"] == b["evidence_fingerprint"]
    resumed = _result([_row("8/C.P5", achieved=True, runtime=True)])
    assert compute_assessment_state(resumed)["evidence_fingerprint"] != a["evidence_fingerprint"]


# ── finalizer wiring: pause marks the grade, resume clears them ──────────────
def test_finalizer_marks_paused_then_clears_on_resume():
    rows = [
        {**_row("8/C.P5", block=True), "score": 0, "verdict_status": "fail"},
        {**_row("8/C.M3", block=True), "score": 0, "verdict_status": "fail"},
    ]
    grading = _result(rows, blockers=[DEP], status="paused")
    finalize_grading_criteria_results(grading, artifact_inventory=grading["artifact_inventory"])
    assert grading["assessment_state"]["state"] == "PAUSED"
    assert grading["grade_decision_status"] == "PAUSED"
    assert grading["final_grade_allowed"] is False
    assert grading["official_grade_provisional"] is True
    for r in grading["criteria_results"]:
        assert r["verification_status"] == NOT_VERIFIED_BLOCKED
        assert r["award_block_reason"] == "runtime_blocked"

    # resume: the blocker is gone and the run produced a verdict
    grading["artifact_inventory"]["runtime_observation_report"] = {"status": "completed", "runtime_observed": True}
    finalize_grading_criteria_results(grading, artifact_inventory=grading["artifact_inventory"])
    assert grading["assessment_state"]["state"] == "FINAL"
    assert "final_grade_allowed" not in grading
    assert grading.get("grade_decision_status") != "PAUSED"


def test_orchestrator_deletes_generated_build_even_when_play_fails(tmp_path, monkeypatch):
    import app.runtime.orchestrator as orch

    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(orch, "is_l4_sandbox_permitted", lambda *a, **k: True)
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: tmp_path / "Unity")

    def fake_build(cfg):
        cfg.output_exe.parent.mkdir(parents=True, exist_ok=True)
        cfg.output_exe.write_bytes(b"MZ")
        return {"success": True, "artifact": str(cfg.output_exe)}

    monkeypatch.setattr(unity_engine, "run_unity_build", fake_build)
    monkeypatch.setattr(
        unity_engine, "run_unity_play_session", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    result = orch.run_runtime_session("stu", proj, timeout_seconds=5)
    generated = result["signals"]["executable"]
    assert result["temp_artifacts"]
    assert not Path(generated).exists()


# ── launcher preflight: exe present but host cannot launch it ────────────────
def test_godot_exe_present_but_host_cannot_launch_pauses(tmp_path, monkeypatch):
    root = tmp_path / "game"
    root.mkdir()
    (root / "project.godot").write_text("config_version=5\n")
    (root / "P_03.exe").write_bytes(b"MZ" + b"\0" * 200)
    (root / "P_03.pck").write_bytes(b"GDPC")
    monkeypatch.setattr(deps, "can_launch_windows_exe", lambda: False)
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: tmp_path / "godot")
    monkeypatch.setattr(
        "app.runtime_observation_sandbox.smoke_test_windows_exe",
        lambda *a, **k: pytest.fail("the exe must not be launched"),
    )
    s = _session("godot", root)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.WINDOWS_LAUNCHER_MISSING]


def test_unity_exe_present_but_host_cannot_launch_pauses(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(deps, "can_launch_windows_exe", lambda: False)
    s = _session("unity", proj)
    s.signals["executable"] = str(tmp_path / "Game.exe")
    s.signals["project_root"] = str(proj)
    monkeypatch.setattr(
        unity_engine, "run_unity_play_session", lambda *a, **k: pytest.fail("must not launch")
    )
    unity_engine.UnityRuntimeEngine().execute(s, timeout_seconds=5)
    assert s.status is SessionStatus.PAUSED
    assert _blocker_codes(s) == [deps.WINDOWS_LAUNCHER_MISSING]


def test_unity_source_does_not_build_an_exe_the_host_cannot_run(tmp_path, monkeypatch):
    proj = _unity_project(tmp_path / "CatRunner")
    monkeypatch.setattr(deps, "can_launch_windows_exe", lambda: False)
    monkeypatch.setattr(unity_engine, "resolve_unity_binary", lambda: tmp_path / "Unity")
    monkeypatch.setattr(
        unity_engine, "run_unity_build", lambda cfg: pytest.fail("must not build")
    )
    s = _session("unity", proj)
    eng = unity_engine.UnityRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=5)
    assert _blocker_codes(s) == [deps.WINDOWS_LAUNCHER_MISSING]


def test_launcher_pause_is_blocked_never_not_achieved():
    rows = [_row("8/C.P5", block=True), _row("8/C.M3", block=True)]
    blocker = {
        "code": deps.WINDOWS_LAUNCHER_MISSING, "kind": "MISSING_DEPENDENCY",
        "detail": "cannot launch", "resolvable_by": "install",
    }
    st = compute_assessment_state(_result(rows, blockers=[blocker], status="paused"))
    assert st["state"] == "PAUSED" and not st["final_grade_allowed"]
    assert set(st["decided"].values()) == {NOT_VERIFIED_BLOCKED}


# ── gated: not a dependency, but never a final grade or a student failure ────
@pytest.mark.parametrize("status", ["gated", "skipped"])
def test_gated_or_skipped_run_is_never_final_or_not_achieved(status):
    rows = [{**_row("8/C.P5", block=True), "score": 0}, {**_row("8/C.M3", block=True), "score": 0}]
    grading = _result(rows, status=status)
    finalize_grading_criteria_results(grading, artifact_inventory=grading["artifact_inventory"])
    st = grading["assessment_state"]
    assert st["state"] in ("PAUSED", "PROVISIONAL")
    assert st["final_grade_allowed"] is False
    assert NOT_ACHIEVED_BY_RUNTIME not in st["decided"].values()
    assert grading["official_grade_provisional"] is True
