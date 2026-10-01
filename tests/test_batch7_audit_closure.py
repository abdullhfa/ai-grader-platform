"""Batch 7: close the Final Audit findings.

Find executable -> Run -> Test -> Grade | No executable -> Temporary Build -> Run -> Test -> Grade |
Dependency unavailable -> PAUSED -> preserve state -> dependency available -> Resume -> Run -> Test -> Grade.
Never: Cannot Run -> Static Analysis -> Final Grade.
"""
from __future__ import annotations

import copy
import json
import types
import zipfile
from pathlib import Path

import pytest

import app.auto_resume as ar
from app.assessment_state import compute_assessment_state, run_launch_evidence
from app.criteria_result_finalizer import (
    finalize_grading_criteria_results,
    sync_criteria_results_to_db,
)
from app.final_output_gate import (
    WITHHELD_GRADE, WITHHELD_LABEL, final_grade_allowed, output_grade_label, summary_grade,
)
from app.grading_mode_policy import compact_snapshot_for_storage
from app.official_grade import resolve_official_grade
from app.runtime_provenance_gate import evaluate_provenance_binding
from test_independent_review_governance import (
    COMPARISON, DEP, PROVENANCE, _base, _row, final_result, paused_result,
)
from test_runtime_gate_fail_closed import V2_OK, _finalize, _grading
from test_uniform_m3_d3_governance import _gamemaker_versions

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _state_for(report):
    g = _base([_row("8/C.P5", block=True), _row("8/C.M3", block=True)], report=report)
    return g["assessment_state"]


# ═══ F1 — runtime truth: a status is not a launch ═══════════════════════════
# Report shapes below are what the real engines produce when nothing was launched
# (captured from run_runtime_observation on static fallbacks).
STATIC_REPORTS = {
    "godot_static_only": {"status": "completed", "runtime_observed": False, "runtime_verified": False,
                          "observation_mode": "orchestrated_runtime_v2", "artifact_analyses": []},
    "godot_apk_pck_static_scan": {"status": "completed", "runtime_observed": False, "runtime_verified": False,
                                  "artifact_analyses": [{"artifact": "g.pck"}, {"artifact": "g.apk"}]},
    "unity_static_fallback": {"status": "completed", "observation_mode": "orchestrated_runtime_v2"},
    "scratch_static_only": {"status": "completed", "observation_mode": "orchestrated_runtime_v2"},
    "gamemaker_source_only": {"status": "completed", "game_launch_attempted": False,
                              "runtime_method": "gamemaker_pro_runtime_verification"},
    "partial_without_launch": {"status": "partial", "game_launch_attempted": False},
    "failed_without_launch": {"status": "failed"},
}


@pytest.mark.parametrize("name", sorted(STATIC_REPORTS))
def test_static_or_unlaunched_report_is_never_final_or_not_achieved(name):
    st = _state_for(STATIC_REPORTS[name])
    assert st["state"] != "FINAL" and st["final_grade_allowed"] is False
    assert set(st["decided"].values()) == {"NOT_VERIFIED_BLOCKED"}, name
    assert "NOT_ACHIEVED_BY_RUNTIME" not in st["decided"].values()
    assert run_launch_evidence({"artifact_inventory": {"runtime_observation_report": STATIC_REPORTS[name]}}) is False


@pytest.mark.parametrize("report", [
    {"status": "crashed", "game_launch_attempted": True},
    {"status": "failed", "runtime_observed": True},
    {"status": "completed", "artifact_analyses": [{"attempted": True, "smoke_result": "early_exit"}]},
    {"status": "partial", "runtime_screenshots": [{"status": "captured", "path": "x.png"}]},
    {"status": "completed", "gameplay_verification": {"l4_level": "L3"}},
])
def test_a_real_launch_followed_by_a_real_failure_can_be_not_achieved(report):
    st = _state_for(report)
    assert st["decided"]["P5"] == "NOT_ACHIEVED_BY_RUNTIME" and st["state"] == "FINAL"


def test_an_environment_fault_analysis_is_not_a_launch():
    report = {"status": "completed", "artifact_analyses": [{"attempted": True, "environment_fault": "wine_platform_fault"}]}
    assert _state_for(report)["decided"]["P5"] == "NOT_VERIFIED_BLOCKED"


def _l4_permitted(monkeypatch):
    import app.runtime.orchestrator as orch

    monkeypatch.setattr(orch, "is_l4_sandbox_permitted", lambda *a, **k: True)
    return orch


def test_real_scratch_static_engine_output_is_not_final(tmp_path, monkeypatch):
    orch = _l4_permitted(monkeypatch)
    sb3 = tmp_path / "s" / "g.sb3"
    sb3.parent.mkdir()
    with zipfile.ZipFile(sb3, "w") as z:
        z.writestr("project.json", json.dumps({"targets": [{"isStage": True, "name": "Stage", "blocks": {}, "variables": {}}], "meta": {}}))
    obs = orch.run_runtime_observation([str(sb3)], student_name="scratch_b7", grading_mode="deep")
    st = _state_for(obs)
    assert st["state"] != "FINAL" and "NOT_ACHIEVED_BY_RUNTIME" not in st["decided"].values()


def test_real_gamemaker_source_only_engine_output_is_not_final(tmp_path, monkeypatch):
    orch = _l4_permitted(monkeypatch)
    proj = tmp_path / "gm"
    proj.mkdir()
    (proj / "Game.yyp").write_text('{"MetaData":{"IDEVersion":"2023.1"},"resources":[]}')
    (proj / "scr.gml").write_text("x = 1;")
    obs = orch.run_runtime_observation([str(p) for p in proj.rglob("*") if p.is_file()],
                                       student_name="gm_b7", grading_mode="deep")
    st = _state_for(obs)
    assert st["state"] != "FINAL" and "NOT_ACHIEVED_BY_RUNTIME" not in st["decided"].values()


# ═══ F2 — nothing is exported as FINAL while PAUSED ═════════════════════════
def test_final_grade_allowed_rules():
    assert final_grade_allowed(final_result()) is True
    assert final_grade_allowed(paused_result()) is False
    assert final_grade_allowed({"final_grade_allowed": False}) is False
    assert final_grade_allowed({"assessment_state": {"state": "PROVISIONAL"}}) is False
    assert final_grade_allowed({"grade_decision_status": "PAUSED"}) is False
    assert final_grade_allowed({"grade_level": "M"}) is True  # legacy/non-game: never invents a block
    assert final_grade_allowed(None) is True


def test_gate_helpers_withhold_the_grade():
    paused = paused_result()
    assert summary_grade(paused, "M") == WITHHELD_GRADE
    assert output_grade_label(paused, "BTEC M") == WITHHELD_LABEL
    final = final_result()
    assert summary_grade(final, "P") == "P" and output_grade_label(final, "BTEC P") == "BTEC P"


def test_official_grade_used_by_pdf_and_word_is_withheld_while_paused():
    paused = paused_result()
    internal_grade = paused["grade_level"]
    official = resolve_official_grade(copy.deepcopy(paused), reapply_pipeline=True)
    assert official.final is False and official.grade_label == WITHHELD_LABEL
    assert official.grade in ("U", "P", "M", "D")  # provisional letter stays internal
    final = resolve_official_grade(copy.deepcopy(final_result()), reapply_pipeline=True)
    assert final.final is True and final.grade_label.startswith("BTEC ")
    assert paused["grade_level"] == internal_grade  # the internal result is preserved for resume


def test_pdf_and_word_use_the_gated_label():
    pdf = (ROOT / "app/report_generator.py").read_text(encoding="utf-8")
    word = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "grade_level = official.grade_label" in pdf  # the gated label
    assert "output_grade_label(_gdm_snap, grade_level)" in word  # summary path of the Word report


def test_lms_export_never_exports_a_paused_grade_as_final():
    from app.governance.lms_export import build_lms_export_rows

    paused = {"student_name": "a", "grade_level": "M", "percentage": 80, **{
        "assessment_state": paused_result()["assessment_state"], "final_grade_allowed": False}}
    final = {"student_name": "b", "grade_level": "P", "percentage": 60}
    rows = {r["student_name"]: r for r in build_lms_export_rows([paused, final])}
    assert rows["a"]["grade_level"] == "" and rows["a"]["percentage"] == "" and rows["a"]["grade_status"] == WITHHELD_GRADE
    assert rows["b"]["grade_level"] == "P" and rows["b"]["grade_status"] == "FINAL"
    snap_wrapped = {"student_name": "c", "grade_level": "D", "snapshot": paused_result()}
    assert build_lms_export_rows([snap_wrapped])[0]["grade_level"] == ""


def test_db_summary_never_stores_a_paused_grade():
    summary = types.SimpleNamespace(grade_level="U", percentage=0.0, total_score=0)

    class _Q:
        def __init__(self, rows): self.rows = rows
        def filter(self, *a): return self
        def all(self): return self.rows
        def first(self): return self.rows[0] if self.rows else None

    class _DB:
        def query(self, model):
            return _Q([types.SimpleNamespace(criteria=None)]) if model.__name__ == "GradingResult" else _Q([summary])
        def commit(self): pass

    paused = paused_result()
    paused["grade_level"] = "M"
    sync_criteria_results_to_db(_DB(), 1, paused)
    assert summary.grade_level == WITHHELD_GRADE
    final = final_result()
    final["grade_level"] = "P"
    sync_criteria_results_to_db(_DB(), 1, final)
    assert summary.grade_level == "P"
    wr = (ROOT / "app/batch_grade_worker.py").read_text(encoding="utf-8")
    assert 'summary_grade(result, str(result.get("grade_level") or ""))' in wr


def test_the_batch_ui_shows_no_grade_badge_for_a_non_final_result():
    html = (ROOT / "app/templates/batch_results.html").read_text(encoding="utf-8")
    assert "og.get('final') is sameas false" in html


# ═══ F3 — compaction keeps the runtime truth ═════════════════════════════════
@pytest.mark.parametrize("mode", ["deep", "fast", "basic", "pro"])
def test_paused_with_blockers_survives_storage_and_refinalization(mode):
    g = paused_result()
    stored = compact_snapshot_for_storage(json.loads(json.dumps(g)), mode)
    assert stored["assessment_state"]["state"] == "PAUSED"
    finalize_grading_criteria_results(stored, artifact_inventory=stored.get("artifact_inventory"))
    st = stored["assessment_state"]
    assert st["state"] == "PAUSED" and [b["code"] for b in st["blockers"]] == [DEP["code"]]
    assert st["final_grade_allowed"] is False
    rep = stored["artifact_inventory"]["runtime_observation_report"]
    assert rep["provenance"] == PROVENANCE and rep["runtime_blockers"][0]["code"] == DEP["code"]
    assert st["blockers"], "blockers must not be lost by storage"


@pytest.mark.parametrize("mode", ["fast", "basic"])
def test_launch_evidence_survives_storage(mode):
    stored = compact_snapshot_for_storage(json.loads(json.dumps(final_result())), mode)
    finalize_grading_criteria_results(stored, artifact_inventory=stored.get("artifact_inventory"))
    assert stored["assessment_state"]["state"] == "FINAL"
    assert stored["assessment_state"]["decided"]["M3"] == "NOT_ACHIEVED_BY_RUNTIME"  # real run, real negative
    assert run_launch_evidence(stored) is True


# ═══ F4 — production auto resume ═════════════════════════════════════════════
class _Sub:
    def __init__(self, snap, sid=7):
        self.id, self.grading_snapshot_json = sid, json.dumps(snap, default=str)


class _FakeDB:
    def __init__(self, subs): self.subs, self.commits = subs, 0
    def query(self, *_a): return self
    def filter(self, *_a): return self
    def limit(self, *_a): return self
    def all(self): return self.subs
    def commit(self): self.commits += 1
    def close(self): pass


def _stored_paused(tmp_path, *, files=True):
    game = tmp_path / "game.exe"
    if files:
        game.write_bytes(b"MZ")
    g = paused_result()
    g["submission_paths"] = [str(game), "Test plan.docx"]
    g["provenance_history"] = []
    return g


def _sweep_env(monkeypatch, subs, build):
    import app.database as database
    import app.artifact_inventory as inventory_mod

    db = _FakeDB(subs)
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(inventory_mod, "build_artifact_inventory", build)
    synced = []
    monkeypatch.setattr("app.criteria_result_finalizer.sync_criteria_results_to_db",
                        lambda d, sid, snap: synced.append(sid) or {})
    return db, synced


def test_sweep_leaves_a_still_blocked_result_paused_and_runs_nothing(tmp_path, monkeypatch):
    monkeypatch.setitem(ar._CHECKS, DEP["code"], lambda: False)
    sub = _Sub(_stored_paused(tmp_path))
    before = sub.grading_snapshot_json
    calls = []
    _db, synced = _sweep_env(monkeypatch, [sub], lambda **k: calls.append(k) or {})
    assert ar.sweep_paused_results() == [] and calls == [] and synced == []
    assert sub.grading_snapshot_json == before
    assert json.loads(sub.grading_snapshot_json)["assessment_state"]["state"] == "PAUSED"


def test_sweep_resumes_only_the_saved_phase_when_the_blocker_clears(tmp_path, monkeypatch):
    monkeypatch.setitem(ar._CHECKS, DEP["code"], lambda: True)
    snap = _stored_paused(tmp_path)
    snap["student_text"] = "AI graded text kept"
    sub = _Sub(snap)
    calls = []

    def fake_inventory(**kw):
        calls.append(kw)
        return {"runtime_observation_report": {"status": "completed", "runtime_observed": True,
                                               "game_launch_attempted": True, "provenance": PROVENANCE,
                                               "version_runtime_comparison": COMPARISON}}

    db, synced = _sweep_env(monkeypatch, [sub], fake_inventory)
    assert ar.sweep_paused_results() == [7]
    assert len(calls) == 1 and calls[0]["submission_paths"][0].endswith("game.exe")  # only runtime/inventory phase
    saved = json.loads(sub.grading_snapshot_json)
    assert saved["assessment_state"]["state"] != "PAUSED"
    assert saved["student_text"] == "AI graded text kept"
    assert len(saved["provenance_history"]) == 1  # the paused run's provenance is archived, not lost
    assert saved["provenance_history"][0]["blockers"][0]["code"] == DEP["code"]
    assert synced == [7] and db.commits == 1


def test_sweep_cooldown_prevents_hot_looping_after_a_failed_attempt(tmp_path, monkeypatch):
    monkeypatch.setitem(ar._CHECKS, DEP["code"], lambda: True)
    sub = _Sub(_stored_paused(tmp_path))
    calls = []

    def failing(**kw):
        calls.append(1)
        raise RuntimeError("runtime exploded")

    _sweep_env(monkeypatch, [sub], failing)
    assert ar.sweep_paused_results(now=1_000_000.0) == []
    assert ar.sweep_paused_results(now=1_000_010.0) == []  # inside the cooldown: no second run
    assert len(calls) == 1
    assert json.loads(sub.grading_snapshot_json)["assessment_state"]["state"] == "PAUSED"


def test_sweep_does_not_resume_when_the_submission_files_are_gone(tmp_path, monkeypatch):
    monkeypatch.setitem(ar._CHECKS, DEP["code"], lambda: True)
    sub = _Sub(_stored_paused(tmp_path, files=False))
    calls = []
    _sweep_env(monkeypatch, [sub], lambda **k: calls.append(k) or {})
    assert ar.sweep_paused_results() == [] and calls == []
    assert json.loads(sub.grading_snapshot_json)["assessment_state"]["state"] == "PAUSED"


def test_provisional_without_blockers_is_not_resumed():
    g = _base([_row("8/C.M3", block=True)], report={"status": "gated"})
    assert g["assessment_state"]["state"] == "PROVISIONAL"
    out = ar.resume_paused_grading_result(g, build_inventory=lambda **k: pytest.fail("must not run"))
    assert out["resumed"] is False and out["reason"] == "no_blockers_to_clear"


def test_the_production_loop_runs_the_result_sweep():
    src = (ROOT / "app/auto_resume.py").read_text(encoding="utf-8")
    loop = src.split("async def run_auto_resume_loop")[1]
    assert "auto_resume_paused_results()" in loop
    assert "run_auto_resume_loop" in (ROOT / "main.py").read_text(encoding="utf-8")


# ═══ V1 / V2 / build provenance gate for P5, P6, M3 ═════════════════════════
def _gate_inputs(tmp_path, monkeypatch, report_extra):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)  # real V1/V2 trees: the M3 code diff can pass
    grading, inv = _grading(root, l4=True)
    inv["runtime_observation_report"] = {"status": "completed", "game_launch_attempted": True,
                                         "runtime_observed": True, **report_extra}
    return grading, inv


def _rows(grading):
    return {r["criteria_level"]: r for r in grading["criteria_results"]}


def test_attributable_v2_evidence_with_a_comparable_pair_opens_the_gate(tmp_path, monkeypatch):
    grading, inv = _gate_inputs(tmp_path, monkeypatch, {"provenance": PROVENANCE, "version_runtime_comparison": COMPARISON})
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.P5"]["achieved"] and by["8/C.M3"]["achieved"]
    assert evaluate_provenance_binding(grading)["blocked"] == {}


def test_legacy_results_without_provenance_are_not_re_judged(tmp_path, monkeypatch):
    grading, inv = _gate_inputs(tmp_path, monkeypatch, {})
    assert evaluate_provenance_binding(grading)["applies"] is False
    assert _finalize(grading, inv, monkeypatch)["8/C.P5"]["achieved"]


@pytest.mark.parametrize("label,prov,cmp_patch,expect_status,expect_code", [
    ("unbound to V2", {**PROVENANCE, "version_label": None}, {}, "NOT_VERIFIED_BLOCKED", "gating_evidence_version_unbound"),
    ("bound to V1", {**PROVENANCE, "version_label": "V1"}, {}, "NOT_VERIFIED_BLOCKED", "gating_evidence_version_unbound"),
    ("provenance mismatch", PROVENANCE, {"status": "PROVENANCE_MISMATCH",
        "provenance_mismatches": [{"version": "V2", "code": "build_from_different_version_folder"}]},
        "PROVENANCE_MISMATCH", "version_provenance_mismatch"),
    ("gating build is not the V2 build", {**PROVENANCE, "build_provenance": {
        "kind": "student_supplied", "executable": {"sha256": "other", "exists": True}}}, {},
        "PROVENANCE_MISMATCH", "gating_build_differs_from_v2"),
    ("collection failed", {"schema": "x", "error": "boom"}, {}, "NOT_VERIFIED_BLOCKED", "provenance_unavailable"),
])
def test_unattributable_runtime_evidence_never_opens_p5_p6_m3(tmp_path, monkeypatch, label, prov, cmp_patch, expect_status, expect_code):
    cmp = {**COMPARISON, **cmp_patch}
    grading, inv = _gate_inputs(tmp_path, monkeypatch, {"provenance": prov, "version_runtime_comparison": cmp})
    by = _finalize(grading, inv, monkeypatch)
    for lvl in ("8/C.P5", "8/C.P6", "8/C.M3"):
        assert by[lvl]["achieved"] is False and by[lvl]["award_block_reason"] == "provenance_unverified", (label, lvl)
        assert by[lvl]["provenance_binding"]["status"] == expect_status and by[lvl]["provenance_binding"]["code"] == expect_code
    assert by["8/BC.D3"]["achieved"] is False  # D3 follows M3
    st = grading["assessment_state"]
    assert set(st["decided"].values()) == {"NOT_VERIFIED_BLOCKED"} and st["final_grade_allowed"] is False
    assert expect_code in [b["code"] for b in st["blockers"]]
    assert "NOT_ACHIEVED_BY_RUNTIME" not in st["decided"].values()


def test_v1_not_run_blocks_only_m3_and_identical_builds_block_only_m3():
    v1_blocked = {**COMPARISON, "status": "BLOCKED", "v1": {**COMPARISON["v1"], "run_state": "PAUSED"}}
    g = {"artifact_inventory": {"runtime_observation_report": {"provenance": PROVENANCE, "version_runtime_comparison": v1_blocked}}}
    assert set(evaluate_provenance_binding(g)["blocked"]) == {"M3"}
    identical = {**COMPARISON, "status": "IDENTICAL_BUILD", "identical_build": True}
    g = {"artifact_inventory": {"runtime_observation_report": {"provenance": PROVENANCE, "version_runtime_comparison": identical}}}
    assert set(evaluate_provenance_binding(g)["blocked"]) == {"M3"}


def test_provenance_blockers_clear_only_on_a_new_upload():
    blocker = {"code": "version_provenance_mismatch", "kind": "PROVENANCE", "detail": "x", "resolvable_by": "upload"}
    assert ar.blocker_cleared(blocker) is False
    assert ar.blocker_cleared(blocker, submission_changed=True) is True


def test_v1_and_v2_are_never_merged_by_the_binding():
    g = {"artifact_inventory": {"runtime_observation_report": {"provenance": PROVENANCE, "version_runtime_comparison": COMPARISON}}}
    before = copy.deepcopy(g)
    out = evaluate_provenance_binding(g)
    assert g == before and out["bound_version"] == "V2"
    assert COMPARISON["evidence_merge_allowed"] is False
