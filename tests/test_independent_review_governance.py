"""Batch 5: deterministic decides; the AI review is auxiliary and can never change the result."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.assessment_state import compute_assessment_state
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.independent_review import (
    REL_AGREE, REL_DISAGREE, REL_NOT_COMPARABLE,
    deterministic_review, run_governed_secondary_review,
)

ROOT = Path(__file__).resolve().parent.parent
DEP = {"code": "unity_editor_missing", "kind": "MISSING_DEPENDENCY",
       "detail": "Unity Editor", "resolvable_by": "install"}
PROVENANCE = {"schema": "runtime_provenance_v1",
              "source_provenance": {"available": True, "tree_hash": "abc"},
              "build_provenance": {"kind": "student_supplied", "executable": {"sha256": "f00d"}},
              "mismatches": []}
COMPARISON = {"schema": "runtime_version_comparison_v1", "status": "COMPARABLE",
              "v1": {"version": "V1"}, "v2": {"version": "V2"}, "evidence_merge_allowed": False}


class FakeReviewer:
    provider = "deepseek"
    model = "fake"

    def __init__(self, reviews=None, error=None):
        self.reviews, self.error = reviews or [], error

    def chat_completion(self, messages, **kwargs):
        if self.error:
            raise self.error
        return json.dumps({"criteria_reviews": self.reviews}, ensure_ascii=False)


def _row(level, *, achieved=False, runtime=False, block=False, score=None):
    return {"criteria_level": level, "achieved": achieved, "awardable": achieved,
            "runtime_l4_verified": runtime, "runtime_gate_block": block,
            "score": score if score is not None else (75 if achieved else 0),
            "verdict_status": "pass" if achieved else "fail", "feedback": "primary text"}


def _base(rows, *, report, paths=("game.exe", "Test plan.docx")):
    inv = {"runtime_observation_report": report, "assets_detected": {"word_pdf": True}}
    g = {"criteria_results": rows, "artifact_inventory": inv, "submission_paths": list(paths),
         "grading_mode": "deep", "grade_level": "P",
         "primary_ai_grader": {"provider": "gemini", "model": "g"}}
    finalize_grading_criteria_results(g, artifact_inventory=inv)
    return g


def final_result():
    """Runtime really ran: P5 verified by runtime, M3 really not achieved."""
    rep = {"status": "completed", "provenance": PROVENANCE, "version_runtime_comparison": COMPARISON}
    g = _base([_row("8/C.P5", achieved=True, runtime=True), _row("8/C.M3", block=True),
               _row("8/B.M2", achieved=True)], report=rep)
    assert g["assessment_state"]["state"] == "FINAL"
    assert g["assessment_state"]["decided"]["M3"] == "NOT_ACHIEVED_BY_RUNTIME"
    return g


def paused_result():
    rep = {"status": "paused", "runtime_blockers": [DEP], "provenance": PROVENANCE,
           "version_runtime_comparison": COMPARISON}
    g = _base([_row("8/C.P5", block=True), _row("8/C.M3", block=True), _row("8/B.M2", achieved=True)], report=rep)
    assert g["assessment_state"]["state"] == "PAUSED"
    return g


def _review(g, reviews, **kw):
    return run_governed_secondary_review(
        g, student_text="t", grading_criteria=[], reviewer_provider=FakeReviewer(reviews),
        force_enabled=True, **kw)


def _core(g):
    """Everything except the review annotations."""
    d = copy.deepcopy(g)
    d.pop("independent_review", None)
    d.pop("secondary_ai_review", None)
    for row in d["criteria_results"]:
        row.pop("secondary_ai_review", None)
    return d


# ── 1. deterministic alone decides ───────────────────────────────────────────
def test_deterministic_alone_produces_the_final_decision():
    g = final_result()
    before = _core(g)
    audit = run_governed_secondary_review(g, student_text="t", grading_criteria=[])  # AI disabled
    assert audit["status"] == "DISABLED"
    det = g["independent_review"]["deterministic"]
    assert det["final_decision"] is True and det["final_grade_allowed"] is True
    assert det["decisions"]["P5"]["decision"] == "ACHIEVED"
    assert det["decisions"]["M3"]["decision"] == "NOT_ACHIEVED"
    assert g["independent_review"]["decision_authority"] == "DETERMINISTIC"
    assert _core(g) == before


def test_deterministic_review_is_pure():
    g = final_result()
    before = copy.deepcopy(g)
    deterministic_review(g)
    assert g == before


# ── 2. AI alone cannot change the result ─────────────────────────────────────
def test_ai_positive_cannot_replace_a_real_not_achieved_by_runtime():
    g = final_result()
    before = _core(g)
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.99, "reasoning": "looks fine"}])
    m3 = next(r for r in g["criteria_results"] if r["criteria_level"] == "8/C.M3")
    assert m3["achieved"] is False and m3["score"] == 0
    assert _core(g) == before  # grade, status, state, rows all untouched
    c = g["independent_review"]["auxiliary_ai_review"]["disagreements"][0]
    assert c["deterministic"] == "NOT_ACHIEVED" and c["ai_achieved"] is True
    assert c["ai_positive_ignored"] is True and c["effect"] == "none"


# ── 3. agreement: no unnecessary change ──────────────────────────────────────
def test_agreement_changes_nothing():
    g = final_result()
    before = _core(g)
    _review(g, [{"criterion": "M2", "achieved": True, "confidence": 0.9, "reasoning": "ok"},
                {"criterion": "M3", "achieved": False, "confidence": 0.9, "reasoning": "no"}])
    aux = g["independent_review"]["auxiliary_ai_review"]
    assert {c["relation"] for c in aux["compared"]} == {REL_AGREE}
    assert aux["disagreements"] == []
    # the legacy reviewer's own status write is blocked and only recorded
    assert set(aux["blocked_writes"]) <= {"grade_decision_status", "official_grade_provisional"}
    assert _core(g) == before


# ── 4. disagreement: recorded only ───────────────────────────────────────────
def test_disagreement_is_recorded_without_changing_the_grade():
    g = final_result()
    before = _core(g)
    _review(g, [{"criterion": "M2", "achieved": False, "confidence": 0.8, "reasoning": "weak"}])
    aux = g["independent_review"]["auxiliary_ai_review"]
    assert [c["relation"] for c in aux["compared"]] == [REL_DISAGREE]
    assert aux["disagreements"][0]["deterministic"] == "ACHIEVED"
    assert g["secondary_ai_review"]["status"] == "DISAGREEMENT_RECORDED"
    m2 = next(r for r in g["criteria_results"] if r["criteria_level"] == "8/B.M2")
    assert m2["achieved"] is True
    assert _core(g) == before


@pytest.mark.parametrize("policy", ["primary", "authoritative", "hold"])
def test_no_policy_can_write_a_grade_or_create_a_hold(monkeypatch, policy):
    monkeypatch.setenv("SECONDARY_REVIEW_DISAGREEMENT_POLICY", policy)
    g = final_result()
    before = _core(g)
    audit = _review(g, [{"criterion": "M2", "achieved": False, "confidence": 0.8, "reasoning": "weak"}])
    assert _core(g) == before
    assert g.get("human_review_required") is None
    assert audit["hold_required"] is False
    assert g["grade_level"] == before["grade_level"]
    assert not any(r.get("secondary_review_hold") for r in g["criteria_results"])


# ── 5. PAUSED / PROVISIONAL never become final ───────────────────────────────
@pytest.mark.parametrize("policy", ["primary", "authoritative", "hold"])
def test_paused_never_becomes_final_because_of_ai_review(monkeypatch, policy):
    monkeypatch.setenv("SECONDARY_REVIEW_DISAGREEMENT_POLICY", policy)
    g = paused_result()
    before = _core(g)
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.99, "reasoning": "fine"},
                {"criterion": "M2", "achieved": True, "confidence": 0.9, "reasoning": "fine"}])
    assert g["assessment_state"]["state"] == "PAUSED"
    assert g["final_grade_allowed"] is False
    assert g["official_grade_provisional"] is True
    assert g["grade_decision_status"] == "PAUSED"
    assert _core(g) == before
    rel = {c["criterion"]: c["relation"] for c in g["independent_review"]["auxiliary_ai_review"]["compared"]}
    assert rel["8/C.M3"] == REL_NOT_COMPARABLE  # a blocked verdict is never filled in by an opinion


def test_provisional_never_becomes_final_because_of_ai_review():
    g = _base([_row("8/C.M3", block=True)], report={"status": "gated"})  # no run happened
    assert g["assessment_state"]["state"] == "PROVISIONAL"
    before = _core(g)
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "fine"}])
    assert g["assessment_state"]["state"] == "PROVISIONAL" and g["final_grade_allowed"] is False
    assert _core(g) == before


def test_paused_reviewer_attempts_are_blocked_and_recorded():
    g = paused_result()
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "x"}])
    blocked = g["independent_review"]["auxiliary_ai_review"]["blocked_writes"]
    assert "official_grade_provisional" in blocked or "grade_decision_status" in blocked


# ── 6. provenance and V1/V2 untouched ────────────────────────────────────────
def test_provenance_and_version_comparison_survive_the_review():
    g = paused_result()
    g["provenance_history"] = [{"provenance": PROVENANCE, "reason": "resumed_after_pause"}]
    inv_before = copy.deepcopy(g["artifact_inventory"])
    hist_before = copy.deepcopy(g["provenance_history"])
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "x"}])
    assert g["artifact_inventory"] == inv_before
    assert g["provenance_history"] == hist_before
    rep = g["artifact_inventory"]["runtime_observation_report"]
    assert rep["provenance"] == PROVENANCE and rep["version_runtime_comparison"] == COMPARISON


def test_a_bad_version_comparison_is_flagged_as_conflict_not_changed():
    rep = {"status": "completed", "version_runtime_comparison": {**COMPARISON, "status": "PROVENANCE_MISMATCH"}}
    g = _base([_row("8/C.P5", achieved=True, runtime=True), _row("8/C.M3", achieved=True, runtime=True)],
              report=rep)
    det = deterministic_review(g)
    assert {"criterion": "M3", "code": "m3_with_unverifiable_version_comparison"} in det["conflicts"]
    assert next(r for r in g["criteria_results"] if r["criteria_level"] == "8/C.M3")["achieved"] is True


def test_d3_without_m3_is_a_recorded_conflict():
    g = final_result()
    d3 = _row("8/BC.D3", achieved=True)
    g["criteria_results"].append(d3)
    det = deterministic_review(g)
    assert {"criterion": "D3", "code": "d3_without_m3"} in det["conflicts"]


# ── 7. failures and teacher_confirmed ────────────────────────────────────────
def test_a_failing_reviewer_leaves_the_result_untouched():
    g = final_result()
    before = _core(g)
    run_governed_secondary_review(
        g, student_text="t", grading_criteria=[],
        reviewer_provider=FakeReviewer(error=RuntimeError("provider down")), force_enabled=True)
    assert g["secondary_ai_review"]["status"] == "REVIEW_UNAVAILABLE"
    assert _core(g) == before


def test_no_dependency_on_teacher_confirmed():
    for name in ("app/independent_review.py", "app/assessment_state.py", "app/auto_resume.py"):
        assert "teacher_confirmed" not in (ROOT / name).read_text(encoding="utf-8"), name
    plain = final_result()
    flagged = final_result()
    flagged["teacher_confirmed"] = True
    other = final_result()
    other["teacher_confirmed"] = False
    a = deterministic_review(plain)["decisions"]
    assert deterministic_review(flagged)["decisions"] == a == deterministic_review(other)["decisions"]
    assert compute_assessment_state(flagged)["state"] == compute_assessment_state(other)["state"]


def test_batch_grader_uses_the_governed_wrapper():
    src = (ROOT / "app/batch_grader.py").read_text(encoding="utf-8")
    assert "run_governed_secondary_review" in src
    assert "from app.secondary_ai_review import run_secondary_review" not in src
