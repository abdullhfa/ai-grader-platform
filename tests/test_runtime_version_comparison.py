"""Batch 4: V1/V2 runtime comparison with source and build provenance."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import app.auto_resume as ar
import app.runtime_provenance as rp
import app.runtime_engines.unity.engine as unity_engine
from app.assessment_state import compute_assessment_state
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.runtime_engines import dependencies as deps
from app.runtime_engines.base import RuntimeSession
from app.runtime_version_comparison import (
    CMP_BLOCKED, CMP_COMPARABLE, CMP_IDENTICAL_BUILD, CMP_PROVENANCE_MISMATCH,
    build_version_record, compare_version_records, run_version_runtime_comparison,
)


@pytest.fixture(autouse=True)
def _tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _version(root: Path, label: str, code: str, exe_bytes: bytes) -> Path:
    d = root / label
    d.mkdir(parents=True)
    (d / "scr_player.gml").write_text(code)
    (d / "game.exe").write_bytes(exe_bytes)
    return d


def _submission(tmp_path, *, v1_code="spd = 4;", v2_code="spd = 6;", b1=b"MZ1", b2=b"MZ2"):
    root = tmp_path / "student"
    _version(root, "V1", v1_code, b1)
    _version(root, "V2", v2_code, b2)
    return root


def _result(exe: Path, *, level="L4_partial", mech=1, status="completed", engine="gamemaker"):
    """A runtime-session result as produced by run_runtime_session (student build)."""
    session = RuntimeSession.create(engine, "k", exe.parent)
    session.signals["executable"] = str(exe)
    session.signals["project_root"] = str(exe.parent)
    return {
        "status": status,
        "provenance": rp.build_runtime_provenance(session),
        "signals": {"legacy_observation": {"artifact_analyses": [{"gameplay_verification": {
            "l4_level": level, "gameplay_entered": True, "mechanics_verified_count": mech,
            "player_movement_verified": True}}]}},
        "blockers": [],
    }


def _runner_for(results):
    def runner(key, group_root, **_kw):
        return results[key.rsplit("__", 1)[1]]
    return runner


# ── provenance record ────────────────────────────────────────────────────────
def test_provenance_of_a_student_build_has_every_required_field(tmp_path):
    proj = _version(tmp_path / "p", "V1", "spd = 4;", b"MZ-student")
    exe = proj / "game.exe"
    res = _result(exe)
    p = res["provenance"]
    assert p["schema"] == "runtime_provenance_v1"
    assert p["source_provenance"]["available"] and p["source_provenance"]["tree_hash"]
    b = p["build_provenance"]
    assert b["kind"] == "student_supplied" and b["built_by"] == "student"
    assert b["executable"]["sha256"] == hashlib.sha256(b"MZ-student").hexdigest()
    assert b["executable"]["name"] == "game.exe" and b["executable"]["size_bytes"] == len(b"MZ-student")
    ident = p["runtime_identity"]
    assert ident["session_id"] and ident["engine"] == "gamemaker"
    assert ident["started_at"] <= ident["finished_at"] and p["timestamp"]
    assert "C.M3" in p["criteria_evidence"]["criteria"]


def test_platform_build_records_the_source_it_was_built_from(tmp_path):
    proj = tmp_path / "CatRunner"
    (proj / "Assets").mkdir(parents=True)
    (proj / "ProjectSettings").mkdir()
    (proj / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.1f1\n")
    (proj / "Assets" / "Player.cs").write_text("class Player {}")
    build = tmp_path / "build" / "game.exe"
    build.parent.mkdir()
    build.write_bytes(b"MZ-built")
    s = RuntimeSession.create("unity", "k", proj)
    s.signals.update(project_root=str(proj), executable=str(build), built_from_source=True)
    p = rp.build_runtime_provenance(s)
    assert p["engine_version"] == "2022.3.1f1"
    assert p["build_provenance"]["kind"] == "platform_built"
    assert p["build_provenance"]["built_from_source_hash"] == p["source_provenance"]["tree_hash"]
    assert p["mismatches"] == []  # built from this exact source by construction


def test_collect_evidence_carries_provenance(tmp_path):
    proj = tmp_path / "g"
    proj.mkdir()
    (proj / "project.godot").write_text('config/features=PackedStringArray("4.6", "GL")\n')
    s = RuntimeSession.create("godot", "k", proj)
    s.signals["project_root"] = str(proj)
    manifest = unity_engine.UnityRuntimeEngine().collect_evidence(s)
    assert manifest["provenance"]["engine_version"] == "4.6"


# ── comparison ───────────────────────────────────────────────────────────────
def test_matching_source_and_build_makes_v1_v2_comparable(tmp_path):
    root = _submission(tmp_path)
    results = {
        "V1": _result(root / "V1" / "game.exe", level="L4_partial", mech=1),
        "V2": _result(root / "V2" / "game.exe", level="L4_full", mech=3),
    }
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["status"] == CMP_COMPARABLE and cmp["improvement_verifiable"] is True
    assert cmp["provenance_mismatches"] == []
    assert cmp["differences"]["mechanics_verified_count"] == {"v1": 1, "v2": 3, "delta": 2}
    assert cmp["improvement_observed"] is True
    assert cmp["v1"]["provenance"]["source_provenance"]["tree_hash"] != \
        cmp["v2"]["provenance"]["source_provenance"]["tree_hash"]


def test_different_builds_never_merge_evidence(tmp_path):
    root = _submission(tmp_path)
    results = {"V1": _result(root / "V1" / "game.exe"), "V2": _result(root / "V2" / "game.exe")}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    h1 = cmp["v1"]["provenance"]["build_provenance"]["executable"]["sha256"]
    h2 = cmp["v2"]["provenance"]["build_provenance"]["executable"]["sha256"]
    assert h1 != h2
    assert cmp["evidence_merge_allowed"] is False and cmp["identical_build"] is False
    assert cmp["v1"]["provenance"]["runtime_identity"]["session_id"] != \
        cmp["v2"]["provenance"]["runtime_identity"]["session_id"]


def test_identical_build_is_flagged_not_treated_as_an_improvement(tmp_path):
    root = _submission(tmp_path, b1=b"MZ-same", b2=b"MZ-same")
    results = {"V1": _result(root / "V1" / "game.exe", mech=2), "V2": _result(root / "V2" / "game.exe", mech=2)}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["status"] == CMP_IDENTICAL_BUILD and cmp["identical_build"] is True
    assert cmp["improvement_verifiable"] is False


def test_build_from_another_version_folder_is_a_provenance_mismatch(tmp_path):
    root = _submission(tmp_path)
    # V2's run launched the exe that lives in V1's folder.
    results = {"V1": _result(root / "V1" / "game.exe", mech=1), "V2": _result(root / "V1" / "game.exe", mech=3)}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["status"] == CMP_PROVENANCE_MISMATCH
    assert [(m["version"], m["code"]) for m in cmp["provenance_mismatches"]] == [
        ("V2", rp.MISMATCH_DIFFERENT_VERSION_FOLDER)
    ]
    assert cmp["improvement_verifiable"] is False and cmp["improvement_observed"] is None
    assert cmp["differences"] is not None  # numbers stay visible, they just prove nothing


def test_source_modified_after_build_is_a_provenance_mismatch(tmp_path):
    root = _submission(tmp_path)
    old = 1_600_000_000
    os.utime(root / "V2" / "game.exe", (old, old))  # build much older than its source
    results = {"V1": _result(root / "V1" / "game.exe"), "V2": _result(root / "V2" / "game.exe")}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["status"] == CMP_PROVENANCE_MISMATCH
    assert any(m["code"] == rp.MISMATCH_SOURCE_NEWER and m["version"] == "V2"
               for m in cmp["provenance_mismatches"])


PAUSED_RESULT = {
    "status": "paused",
    "blockers": [{"code": "godot_binary_missing", "kind": "MISSING_DEPENDENCY",
                  "detail": "Godot binary", "resolvable_by": "install"}],
    "provenance": {"source_provenance": {"available": True, "tree_hash": "abc"},
                   "build_provenance": {"kind": "none", "executable": None}, "mismatches": []},
    "signals": {},
}


def test_blocked_side_keeps_the_comparison_blocked_and_never_a_verdict(tmp_path):
    root = _submission(tmp_path)
    results = {"V1": _result(root / "V1" / "game.exe", mech=2), "V2": dict(PAUSED_RESULT)}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["status"] == CMP_BLOCKED
    assert cmp["improvement_observed"] is None and cmp["differences"] is None
    assert [b["code"] for b in cmp["blocked_by"]] == ["godot_binary_missing"]
    assert "NOT_ACHIEVED" not in str(cmp)


def test_v1_and_v2_keep_separate_results(tmp_path):
    root = _submission(tmp_path)
    results = {"V1": _result(root / "V1" / "game.exe", level="L4_partial", mech=2), "V2": dict(PAUSED_RESULT)}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    assert cmp["v1"]["run_state"] == "RAN" and cmp["v1"]["l4"]["mechanics_verified_count"] == 2
    assert cmp["v2"]["run_state"] == "PAUSED" and cmp["v2"]["l4"] is None
    assert cmp["v1"]["provenance"]["version_label"] == "V1"
    assert cmp["v2"]["provenance"]["version_label"] == "V2"


def test_a_crashing_runner_pauses_that_version_instead_of_failing_it(tmp_path):
    root = _submission(tmp_path)

    def runner(key, group_root, **_kw):
        if key.endswith("V2"):
            raise RuntimeError("boom")
        return _result(root / "V1" / "game.exe")

    cmp = run_version_runtime_comparison(root, "stu", runner=runner)
    assert cmp["status"] == CMP_BLOCKED and cmp["v2"]["run_state"] == "PAUSED"


def test_no_version_pair_means_no_comparison(tmp_path):
    (tmp_path / "solo").mkdir()
    (tmp_path / "solo" / "a.gml").write_text("x")
    assert run_version_runtime_comparison(tmp_path / "solo", "stu", runner=lambda *a, **k: {}) is None


def test_blocked_runtime_state_is_not_achieved_free(tmp_path):
    root = _submission(tmp_path)
    results = {"V1": dict(PAUSED_RESULT), "V2": dict(PAUSED_RESULT)}
    cmp = run_version_runtime_comparison(root, "stu", runner=_runner_for(results))
    g = {
        "criteria_results": [{"criteria_level": "8/C.M3", "achieved": False, "awardable": False,
                              "runtime_gate_block": True}],
        "artifact_inventory": {"runtime_observation_report": {
            "status": "paused", "runtime_blockers": PAUSED_RESULT["blockers"],
            "version_runtime_comparison": cmp}},
        "submission_paths": ["a.exe", "Test plan.docx"],
    }
    st = compute_assessment_state(g)
    assert st["state"] == "PAUSED" and st["decided"]["M3"] == "NOT_VERIFIED_BLOCKED"


# ── orchestrator wiring ─────────────────────────────────────────────────────
def test_observation_carries_the_comparison_and_main_provenance(tmp_path, monkeypatch):
    import app.runtime.orchestrator as orch

    root = _submission(tmp_path)
    monkeypatch.setattr(orch, "is_l4_sandbox_permitted", lambda *a, **k: True)
    monkeypatch.setattr(orch, "infer_submission_root", lambda *a, **k: root)
    seen = []

    def fake_session(key, r, **kw):
        seen.append(key)
        return {"status": "paused", "engine": "gamemaker", "blockers": PAUSED_RESULT["blockers"],
                "provenance": PAUSED_RESULT["provenance"], "signals": {}}

    monkeypatch.setattr(orch, "run_runtime_session", fake_session)
    obs = orch.run_runtime_observation([str(root / "V1" / "game.exe")], student_name="stu")
    assert obs["version_runtime_comparison"]["status"] == CMP_BLOCKED
    assert obs["provenance"]["source_provenance"]["tree_hash"] == "abc"
    assert seen[0] == "stu" and set(seen[1:]) == {"stu__V1", "stu__V2"}


# ── provenance survives resume ──────────────────────────────────────────────
def test_provenance_is_kept_after_resume(tmp_path, monkeypatch):
    monkeypatch.setitem(ar._CHECKS, "godot_binary_missing", lambda: True)
    old_prov = PAUSED_RESULT["provenance"]
    inv = {"runtime_observation_report": {
        "status": "paused", "runtime_blockers": PAUSED_RESULT["blockers"], "provenance": old_prov},
        "assets_detected": {"word_pdf": True}}
    g = {"criteria_results": [{"criteria_level": "8/C.P5", "achieved": False, "awardable": False,
                               "runtime_gate_block": True, "score": 0, "feedback": "kept"}],
         "artifact_inventory": inv, "submission_paths": ["g.exe", "Test plan.docx"], "grading_mode": "deep"}
    finalize_grading_criteria_results(g, artifact_inventory=inv)
    assert g["assessment_state"]["state"] == "PAUSED"

    new_prov = {"source_provenance": {"available": True, "tree_hash": "abc"},
                "build_provenance": {"kind": "student_supplied", "executable": {"sha256": "f00d"}},
                "mismatches": []}
    out = ar.resume_paused_grading_result(
        g, build_inventory=lambda **kw: {"runtime_observation_report": {"status": "completed", "provenance": new_prov}},
    )
    assert out["resumed"] is True
    hist = g["provenance_history"]
    assert len(hist) == 1 and hist[0]["provenance"] == old_prov and hist[0]["run_status"] == "paused"
    assert hist[0]["blockers"][0]["code"] == "godot_binary_missing"
    current = g["artifact_inventory"]["runtime_observation_report"]["provenance"]
    assert current["build_provenance"]["executable"]["sha256"] == "f00d"
    assert current["source_provenance"]["tree_hash"] == old_prov["source_provenance"]["tree_hash"]
