"""Commit 2: automatic resume, no manual Complete, Wine launcher + runtime input.

``Cannot Run -> PAUSED -> dependency/evidence available -> automatic resume -> test -> grade``
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import types
from pathlib import Path

import pytest

import app.auto_resume as ar
import app.runtime_wine as rw
from app.assessment_state import compute_assessment_state
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.runtime_engines import dependencies as deps
from app.runtime_engines.base import RuntimeSession, SessionStatus
import app.runtime_engines.godot.engine as godot_engine

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


DEP = {"code": "unity_editor_missing", "kind": "MISSING_DEPENDENCY",
       "detail": "Unity Editor", "resolvable_by": "install"}


def _row(level, *, achieved=False, runtime=False, block=False):
    return {"criteria_level": level, "achieved": achieved, "awardable": achieved,
            "runtime_l4_verified": runtime, "runtime_gate_block": block,
            "score": 75 if achieved else 0, "verdict_status": "pass" if achieved else "fail",
            "feedback": "ai graded text"}


def _paused_result(paths=("game.exe", "Test plan.docx"), blockers=(DEP,)):
    inv = {"runtime_observation_report": {"status": "paused", "runtime_blockers": list(blockers)},
           "assets_detected": {"word_pdf": True}}
    g = {"criteria_results": [_row("8/C.P5", block=True), _row("8/C.M3", block=True)],
         "artifact_inventory": inv, "submission_paths": list(paths), "grading_mode": "deep",
         "student_text": "AI text kept"}
    finalize_grading_criteria_results(g, artifact_inventory=inv)
    assert g["assessment_state"]["state"] == "PAUSED"
    return g


def _boom(*_a, **_k):
    raise AssertionError("must not be called")


# ── 1. automatic resume: result level ────────────────────────────────────────
def test_still_blocked_stays_paused_and_reruns_nothing(monkeypatch):
    monkeypatch.setitem(ar._CHECKS, "unity_editor_missing", lambda: False)
    g = _paused_result()
    out = ar.resume_paused_grading_result(g, build_inventory=_boom, finalize=_boom)
    assert out["resumed"] is False and out["reason"] == "still_blocked"
    assert g["assessment_state"]["state"] == "PAUSED"
    assert g["final_grade_allowed"] is False


def test_blocker_cleared_resumes_only_runtime_and_finalizing(monkeypatch):
    monkeypatch.setitem(ar._CHECKS, "unity_editor_missing", lambda: True)
    g = _paused_result()
    calls = []

    def fake_inventory(**kw):
        calls.append(("inventory", kw["submission_paths"]))
        return {"runtime_observation_report": {"status": "completed"}}

    out = ar.resume_paused_grading_result(g, build_inventory=fake_inventory)
    assert out["resumed"] is True and out["phases"] == ["runtime", "finalizing"]
    assert [c[0] for c in calls] == ["inventory"]
    assert g["student_text"] == "AI text kept"  # AI phases not redone
    assert all(r["feedback"] == "ai graded text" for r in g["criteria_results"])
    assert g["assessment_state"]["state"] != "PAUSED"
    assert g["assessment_state"]["resumed_phases"] == ["runtime", "finalizing"]
    assert g.get("grade_decision_status") != "PAUSED"


def test_resume_is_a_noop_for_a_final_result():
    g = {"assessment_state": {"state": "FINAL"}, "criteria_results": []}
    assert ar.resume_paused_grading_result(g, build_inventory=_boom)["reason"] == "not_paused"


def test_unknown_blocker_is_never_guessed_away():
    assert ar.blocker_cleared({"code": "something_new", "kind": "MISSING_DEPENDENCY"}) is False


def test_missing_upload_resumes_only_when_files_change(tmp_path):
    f = tmp_path / "game.exe"
    f.write_bytes(b"MZ")
    art = {"code": "executable_not_found", "kind": "MISSING_ARTIFACT",
           "detail": "no exe", "resolvable_by": "upload"}
    g = _paused_result(paths=(str(f),), blockers=(art,))
    out = ar.resume_paused_grading_result(g, build_inventory=_boom, finalize=_boom)
    assert out["resumed"] is False
    (tmp_path / "second.exe").write_bytes(b"MZ2")
    f.write_bytes(b"MZ-new-upload")  # a re-upload changes the file signature
    out = ar.resume_paused_grading_result(
        g, submission_paths=[str(f)], build_inventory=lambda **kw: {"runtime_observation_report": {"status": "completed"}},
    )
    assert out["resumed"] is True


def test_emulator_fault_is_only_rejudged_on_a_native_windows_host(monkeypatch):
    b = {"code": "windows_emulator_run_fault", "kind": "ENV_FAULT"}
    monkeypatch.setattr(sys, "platform", "linux")
    assert ar.blocker_cleared(b) is False
    monkeypatch.setattr(sys, "platform", "win32")
    assert ar.blocker_cleared(b) is True


# ── 2. automatic resume: batch level, and no manual Complete anywhere ───────
def _fake_db(monkeypatch):
    class Q:
        def filter(self, *_a): return self
        def first(self): return None

    class DB:
        def query(self, *_a): return Q()
        def commit(self): pass
        def close(self): pass

    monkeypatch.setattr("app.database.SessionLocal", lambda: DB())


def test_paused_checkpoint_stays_paused_while_preflight_blocks(monkeypatch):
    import app.batch_checkpoint as bc

    saved = []
    monkeypatch.setattr(bc, "save_batch_checkpoint", lambda i, d: saved.append(d))
    monkeypatch.setattr(bc, "resume_batch_from_checkpoint", _boom)
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.toolchain.preflight_gamemaker_runtime_dependency",
        lambda files: {"pause_required": True, "pause_reason": "no gamemaker"},
    )
    ck = {"batch_id": 7, "assignment_id": 3, "paused": True, "student_files": []}
    out = asyncio.run(ar.resume_paused_checkpoint(ck, {}))
    assert out["resumed"] is False and out["reason"] == "still_blocked"
    assert ck["paused"] is True


def test_paused_checkpoint_resumes_automatically_when_preflight_passes(monkeypatch):
    import app.batch_checkpoint as bc

    _fake_db(monkeypatch)
    resumed = []

    async def fake_resume(ck, progress):
        resumed.append(dict(ck))
        return True

    monkeypatch.setattr(bc, "save_batch_checkpoint", lambda i, d: None)
    monkeypatch.setattr(bc, "resume_batch_from_checkpoint", fake_resume)
    monkeypatch.setattr("app.batch_progress_store.persist_assignment_progress", lambda *a, **k: None)
    monkeypatch.setattr("app.batch_progress_store.load_assignment_progress", lambda *a: {})
    monkeypatch.setattr(
        "app.runtime_engines.gamemaker.toolchain.preflight_gamemaker_runtime_dependency",
        lambda files: {"pause_required": False},
    )
    ck = {"batch_id": 7, "assignment_id": 3, "paused": True, "pause_kind": "gamemaker_dependency",
          "student_files": [{"name": "a"}]}
    out = asyncio.run(ar.resume_paused_checkpoint(ck, {}))
    assert out["resumed"] is True
    assert "paused" not in resumed[0] and resumed[0]["student_files"] == [{"name": "a"}]


def test_manual_complete_path_is_gone():
    routes = (ROOT / "app/routes/grading.py").read_text(encoding="utf-8")
    html = (ROOT / "app/templates/batch_grade.html").read_text(encoding="utf-8")
    worker = (ROOT / "app/batch_grade_worker.py").read_text(encoding="utf-8")
    assert "batch-grade-complete-gamemaker" not in routes
    assert "complete_gamemaker_installation" not in routes
    assert "gameMakerCompleteBtn" not in html and "batch-grade-complete-gamemaker" not in html
    assert "Complete" not in worker.split("PHASE_LABELS_AR")[1][:1500]
    assert "teacher_confirmed" not in (ROOT / "app/auto_resume.py").read_text(encoding="utf-8")


def test_startup_runs_the_auto_resume_loop():
    assert "run_auto_resume_loop" in (ROOT / "main.py").read_text(encoding="utf-8")


# ── 3. Wine launcher: a real probe, not "installed" ─────────────────────────
class _FakeRT:
    ok = True
    start_error = None
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def env(self): return {}


def _probe(monkeypatch, *, binary="/usr/bin/wine", rc=0, stderr=b""):
    rw.reset_probe_cache()
    monkeypatch.setattr(rw, "wine_binary", lambda: binary)
    monkeypatch.setattr(rw, "WineRuntime", _FakeRT)
    monkeypatch.setattr(
        rw.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=rc, stderr=stderr),
    )
    return rw.probe_wine_launcher(force=True)


def test_wine_probe_not_installed(monkeypatch):
    res = _probe(monkeypatch, binary=None)
    assert res["ok"] is False and "not installed" in res["reason"]


def test_wine_installed_but_cannot_start_is_not_a_launcher(monkeypatch):
    res = _probe(monkeypatch, rc=1, stderr=b"it looks like wine32 is missing")
    assert res["ok"] is False and "wine32 is missing" in res["reason"]


def test_wine_probe_success(monkeypatch):
    assert _probe(monkeypatch)["ok"] is True


def test_broken_wine_pauses_engine_never_fails_student(tmp_path, monkeypatch):
    monkeypatch.undo()  # drop the autouse-free defaults; use real dependency logic
    rw.reset_probe_cache()
    monkeypatch.setattr(rw, "wine_binary", lambda: None)
    monkeypatch.setattr(sys, "platform", "linux")
    root = tmp_path / "g"
    root.mkdir()
    (root / "project.godot").write_text("x")
    (root / "P.exe").write_bytes(b"MZ" + b"\0" * 50)
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: tmp_path / "godot")
    s = RuntimeSession.create("godot", "stu", root)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=3)
    assert s.status is SessionStatus.PAUSED
    assert s.blockers[0].code == deps.WINDOWS_LAUNCHER_MISSING
    assert "wine is not installed" in s.blockers[0].detail
    rw.reset_probe_cache()


# ── 4. failure inside the emulator is a platform fault, not the student's ────
def test_classify_wine_failure_markers():
    assert rw.classify_wine_failure("wine: Unhandled page fault on read access") == "unhandled page fault"
    assert rw.classify_wine_failure("nodrv_CreateWindow") is not None
    assert rw.classify_wine_failure("game printed a normal line") is None


class _FakeProc:
    def __init__(self, exit_code=None): self.exit_code, self.pid = exit_code, 4242
    def poll(self): return self.exit_code


class _SmokeRT(_FakeRT):
    stderr = ""
    exit_code = None
    def launch(self, exe, cwd): return _FakeProc(type(self).exit_code)
    def stderr_text(self): return type(self).stderr


def _smoke(tmp_path, monkeypatch, *, stderr="", exit_code=None):
    import app.runtime_observation_sandbox as sb

    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ" + b"\0" * 100)
    _SmokeRT.stderr, _SmokeRT.exit_code = stderr, exit_code
    monkeypatch.setattr(rw, "WineRuntime", _SmokeRT)
    monkeypatch.setattr(rw, "probe_wine_launcher", lambda **k: {"ok": True, "reason": "x"})
    monkeypatch.setattr(sys, "platform", "linux")
    return sb.smoke_test_windows_exe(exe, timeout=1)


def test_crash_inside_wine_is_environment_fault(tmp_path, monkeypatch):
    out = _smoke(tmp_path, monkeypatch, stderr="wine: Unhandled page fault ... starting debugger...")
    assert out["environment_fault"] == "wine_platform_fault"
    assert out["attempted"] is False and out["smoke_result"] == "environment_fault"


def test_nonzero_exit_under_wine_is_not_read_as_student_failure(tmp_path, monkeypatch):
    out = _smoke(tmp_path, monkeypatch, exit_code=3)
    assert out["environment_fault"] == "wine_platform_fault"
    assert out["smoke_result"] != "early_exit"


def test_game_that_stays_up_under_wine_is_really_run(tmp_path, monkeypatch):
    out = _smoke(tmp_path, monkeypatch)
    assert out.get("environment_fault") is None
    assert out["smoke_result"] == "stable_window" and out["launcher"] == "wine_xvfb"
    assert out["signals"]["runtime_launch_attempted"] is True


def test_engine_pauses_on_emulator_fault_and_state_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "can_launch_windows_exe", lambda: True)
    root = tmp_path / "g"
    root.mkdir()
    (root / "project.godot").write_text("x")
    (root / "P.exe").write_bytes(b"MZ" + b"\0" * 50)
    monkeypatch.setattr(godot_engine, "resolve_godot_binary", lambda: tmp_path / "godot")
    monkeypatch.setattr(
        "app.runtime_observation_sandbox.smoke_test_windows_exe",
        lambda *a, **k: {"attempted": False, "environment_fault": "wine_platform_fault",
                         "wine_stderr_tail": "Unhandled page fault"},
    )
    s = RuntimeSession.create("godot", "stu", root)
    eng = godot_engine.GodotRuntimeEngine()
    eng.prepare(s)
    eng.execute(s, timeout_seconds=3)
    assert s.status is SessionStatus.PAUSED
    assert s.blockers[0].code == deps.EMULATOR_RUN_FAULT and s.blockers[0].kind == "ENV_FAULT"
    g = {"criteria_results": [_row("8/C.P5", block=True)],
         "artifact_inventory": {"runtime_observation_report": {
             "status": "paused", "runtime_blockers": [b.to_dict() for b in s.blockers]}},
         "submission_paths": ["P.exe"]}
    st = compute_assessment_state(g)
    assert st["state"] == "PAUSED" and st["decided"]["P5"] == "NOT_VERIFIED_BLOCKED"


# ── 5. runtime input on Linux/Wine ──────────────────────────────────────────
class _Hands:
    ok = True
    def __init__(self): self.log = []
    def key_hold(self, label, seconds): self.log.append(("hold", label)); return True
    def click(self, x, y): self.log.append(("click", x, y)); return True
    def screen_size(self): return 1000, 500


def test_input_routes_to_xtest_on_linux(monkeypatch):
    import app.gameplay_verifier as gv

    hands = _Hands()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(rw, "_ACTIVE", hands)
    assert gv._key_hold("D", 0.01) is True
    assert gv._key_hold_legacy("SPACE", 0.01) is True
    assert gv._send_key_win(0x0D) is True
    assert gv._click_game_window_center(process_pid=1, artifact_path=Path("x.exe")) is True
    assert gv._click_at_image_position(
        shot={"width": 200, "height": 100}, image_xy=(100, 50), process_pid=1, artifact_path=Path("x.exe")
    ) is True
    assert ("hold", "D") in hands.log and ("hold", "ENTER") in hands.log
    assert ("click", 500, 310) in hands.log and ("click", 500, 250) in hands.log


def test_no_input_without_an_active_wine_run(monkeypatch):
    import app.gameplay_verifier as gv

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(rw, "_ACTIVE", None)
    assert gv._key_hold("D", 0.01) is False
    assert gv._click_game_window_center(process_pid=1, artifact_path=Path("x.exe")) is False


@pytest.mark.skipif(
    not (shutil.which("Xvfb") and Path("/usr/lib/x86_64-linux-gnu/libXtst.so.6").exists()),
    reason="needs Xvfb + libXtst",
)
def test_real_xtest_input_and_screenshot_on_virtual_display():
    with rw.WineRuntime() as rt:
        assert rt.ok, rt.start_error
        assert rt.key_hold("D", 0.05) is True
        assert rt.key_hold("NOPE", 0.05) is False
        assert rt.click(100, 100) is True
        img = rt.grab()
        assert img.size == (1280, 720)
        assert rw.active_runtime() is rt
    assert rw.active_runtime() is None
