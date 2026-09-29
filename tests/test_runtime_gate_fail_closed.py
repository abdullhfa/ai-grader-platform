"""Regression tests: runtime governance must fail CLOSED, and its facts must not be conflated.

1. gate exception  → no runtime-dependent award survives (never fail-open)
2. L5 completion   ≠ teacher confirmation (explicit ``teacher_confirmations`` record)
3. M3 blocked      → D3 blocked at the *row* level (``dependency_blocked_by``)
4. video only      → an evidence PATH, not criterion awardability
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

import app.runtime_evidence_gate as gate
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.runtime_evidence_gate import (
    BTECCriterionMapper,
    apply_runtime_gate_fail_closed,
    evaluate_runtime_evidence,
    read_teacher_confirmations,
    record_teacher_confirmation,
)
from test_uniform_m3_d3_governance import (
    FULL_L4,
    SUPPORTED_DIFF,
    _academic_row,
    _gamemaker_versions,
)

CLAIM_OK = "بعد الاختبار قمت بزيادة سرعة الفأر spd في كود التحكم."
CLAIM_BAD = (
    "قمت بتحسين سرعة الفأر spd. اضفت حماية مؤقتة invincible مع وميض. "
    "قمت بضغط الصوت وتحسين الاداء delta time. اضفت غرفة تعليمية tutorial."
)
V2_OK = "spd = 6;\nif (place_meeting(x, y, obj_wall)) { x -= spd; }\n"


def _rows():
    out = []
    for level, score in (("8/C.P5", 75), ("8/C.P6", 75), ("8/C.M3", 85), ("8/BC.D3", 95)):
        row = _academic_row(level.replace("8/", ""))
        row.update({"criteria_level": level, "achieved": True, "score": score, "verdict_status": "pass"})
        out.append(row)
    return out


def _grading(root: Path, *, text=CLAIM_OK, l4=True, l5=False, video=False, teacher=None):
    inv = {
        "runtime_artifacts": {"gamemaker_detected": True},
        "testing_evidence": {"status": "present", "entries": [{"t": 1}, {"t": 2}]},
        "assets_detected": {"word_pdf": True},
    }
    if l4:
        inv["gameplay_verification"] = dict(FULL_L4)
    if l5:
        inv["l5_human_playtest"] = {"status": "complete_visual"}
    if video:
        inv["gameplay_video_detected"] = True
    doc = root / "Aim C.docx"
    doc.write_bytes(b"docx")
    grading = {
        "grading_mode": "deep",
        "criteria_results": _rows(),
        "artifact_inventory": inv,
        "student_text": text,
        "submission_paths": [str(doc)],
        "intake_relative_paths": ["Aim C.docx"],
        "grade_level": "D",
    }
    for key in teacher or ():
        record_teacher_confirmation(grading, key, confirmed_by="reviewer")
    return grading, inv


def _finalize(grading, inv, monkeypatch, *, raises=False, satisfied=True):
    monkeypatch.setattr(
        gate,
        "evaluate_runtime_evidence",
        lambda *_a, **_k: {
            "status": "PASS" if satisfied else "BLOCKED", "satisfied": satisfied,
            "accepted_evidence": ["x"], "engine_id": "gamemaker", "summary_ar": "",
        },
    )
    if raises:
        def boom(*_a, **_k):
            raise RuntimeError("simulated gate crash")

        monkeypatch.setattr(gate, "apply_runtime_evidence_gate", boom)
    finalize_grading_criteria_results(grading, artifact_inventory=inv)
    return {r["criteria_level"]: r for r in grading["criteria_results"]}


@pytest.fixture()
def versions(tmp_path):
    return _gamemaker_versions(tmp_path, v2_step=V2_OK)


# ── 1. fail-closed ───────────────────────────────────────────────────────────
def test_gate_exception_never_keeps_runtime_dependent_awards(versions, monkeypatch):
    grading, inv = _grading(versions, l4=False)  # a game with NO runtime evidence
    by = _finalize(grading, inv, monkeypatch, raises=True)
    for level in ("8/C.P5", "8/C.P6", "8/C.M3", "8/BC.D3"):
        assert by[level]["achieved"] is False, level
        assert by[level]["awardable"] is False, level
        assert by[level]["achievement_authority"] == "RUNTIME_GATE_ERROR"
        assert by[level]["award_block_reason"] == "runtime_gate_error"
    assert grading["grade_level"] == "U"


def test_gate_exception_is_recorded_and_puts_the_decision_on_hold(versions, monkeypatch):
    grading, inv = _grading(versions, l4=False)
    _finalize(grading, inv, monkeypatch, raises=True)
    err = grading["runtime_gate_error"]
    assert err["status"] == "NOT_VERIFIED"
    assert err["error_type"] == "RuntimeError"
    assert "simulated gate crash" in err["error"]
    assert set(err["blocked"]) == {"8/C.P5", "8/C.P6", "8/C.M3", "8/BC.D3"}
    assert grading["grade_decision_status"] == "HOLD"
    assert grading["official_grade_provisional"] is True
    assert grading["human_review_required"] is True
    assert grading["criteria_finalizer"]["changes"]  # the block is auditable


def test_gate_exception_cannot_turn_an_unverified_submission_into_a_pass(versions, monkeypatch):
    # Before the fix this ended as grade D with every criterion still achieved.
    grading, inv = _grading(versions, l4=False)
    _finalize(grading, inv, monkeypatch, raises=True)
    assert grading["grade_level"] not in {"P", "M", "D"}


def test_fail_closed_fallback_never_raises_and_ignores_non_game_submissions():
    grading = {
        "criteria_results": [{"criteria_level": "P5", "achieved": True, "score": 80}],
        "artifact_inventory": {"documentation": {"status": "present"}},
    }
    err = apply_runtime_gate_fail_closed(grading, ValueError("boom"), artifact_inventory=grading["artifact_inventory"])
    assert err["status"] == "NOT_VERIFIED"
    assert err["reason"] == "not_a_game_submission"
    assert grading["criteria_results"][0]["achieved"] is True  # an essay unit is not gated
    # even garbage input must not raise
    apply_runtime_gate_fail_closed({"criteria_results": "nope"}, ValueError("x"))
    apply_runtime_gate_fail_closed({}, ValueError("x"))


def test_a_later_healthy_gate_clears_the_error_and_reevaluates(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True, teacher=("M3",))
    _finalize(grading, inv, monkeypatch, raises=True)
    assert "runtime_gate_error" in grading
    monkeypatch.undo()  # gate healthy again
    by = _finalize(grading, inv, monkeypatch)
    assert "runtime_gate_error" not in grading
    assert grading.get("grade_decision_status") != "HOLD"
    assert by["8/C.M3"]["achieved"] is True
    assert by["8/BC.D3"]["achieved"] is True  # restored: M3 passes again


def test_internal_l4_evaluation_error_is_fail_closed_and_visible(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True, teacher=("M3",))
    monkeypatch.setattr(
        "app.gameplay_verifier.assess_automated_l4_gate",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("l4 crash")),
    )
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.P5"]["achieved"] is False
    assert by["8/C.M3"]["achieved"] is False
    assert "l4 crash" in grading["runtime_evidence_gate"]["automated_l4_gate"]["error"]


# ── 2. L5 completion ≠ teacher confirmation ─────────────────────────────────
def test_completed_l5_playtest_is_not_a_teacher_confirmation(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True)  # L5 done, nobody confirmed
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is False
    assert by["8/C.M3"]["awardable"] is False
    decisions = {d["criterion"]: d for d in grading["runtime_evidence_gate"]["automated_l4_gate"]["decisions"]}
    assert decisions["M3"]["reason"] == "l5_completed_teacher_confirmation_missing"
    assert "l5_playtest_completed=True" in decisions["M3"]["evidence_chain"]
    assert "teacher_confirmation=missing" in decisions["M3"]["evidence_chain"]
    assert grading["grade_level"] == "P"  # was D before: L5 alone used to award Merit+Distinction


def test_explicit_teacher_confirmation_is_a_separate_recorded_event(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True, teacher=("M3",))
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is True
    decisions = {d["criterion"]: d for d in grading["runtime_evidence_gate"]["automated_l4_gate"]["decisions"]}
    assert "l5_playtest_completed=True" in decisions["M3"]["evidence_chain"]
    assert "teacher_confirmation=recorded" in decisions["M3"]["evidence_chain"]


def test_teacher_confirmation_without_l5_still_needs_runtime_and_code_diff(versions, monkeypatch):
    grading, inv = _grading(versions, l4=False, l5=False, teacher=("M3",))
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is False  # runtime evidence still required


def test_bare_true_or_anonymous_records_do_not_count_as_confirmation():
    assert read_teacher_confirmations({"teacher_confirmations": {"M3": True}}) == {}
    assert read_teacher_confirmations({"teacher_confirmations": {"M3": {"confirmed": True}}}) == {}
    assert read_teacher_confirmations({"teacher_confirmations": {"M3": {"confirmed": True, "confirmed_by": "  "}}}) == {}
    assert read_teacher_confirmations({"teacher_confirmations": {"M3": {"confirmed": "yes", "confirmed_by": "t"}}}) == {}
    assert read_teacher_confirmations({"teacher_confirmations": {"P5": {"confirmed": True, "confirmed_by": "t"}}}) == {}
    ok = {"teacher_confirmations": {"8/C.M3": {"confirmed": True, "confirmed_by": "t"}}}
    assert read_teacher_confirmations(ok) == {"M3": True}


def test_record_teacher_confirmation_validates_its_input():
    grading: dict = {}
    record = record_teacher_confirmation(grading, "C.D3", confirmed_by="Ms. Batoul", note="ok")
    assert grading["teacher_confirmations"]["D3"] == record
    assert record["confirmed"] is True and record["confirmed_at"].endswith("Z")
    with pytest.raises(ValueError):
        record_teacher_confirmation(grading, "P5", confirmed_by="t")
    with pytest.raises(ValueError):
        record_teacher_confirmation(grading, "M3", confirmed_by=" ")


def test_mapper_reports_l5_and_confirmation_as_distinct_facts():
    def run(confirmed, l5):
        return BTECCriterionMapper().evaluate(
            dict(FULL_L4), test_doc_entries=2, functional_smoke_pass=True,
            teacher_confirmed=confirmed, criteria_results=[_academic_row("C.M3")],
            engine_id="unity", code_diff=SUPPORTED_DIFF, l5_playtest_completed=l5,
        )

    assert run(None, True)["criterion_pass"]["M3"] is False
    assert run({"M3": True}, False)["criterion_pass"]["M3"] is True


# ── 3. D3 depends on M3 at the row level ─────────────────────────────────────
def test_d3_is_blocked_on_its_own_row_when_m3_is_blocked(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True, l5=True, teacher=("M3", "D3"))
    by = _finalize(grading, inv, monkeypatch)
    m3, d3 = by["8/C.M3"], by["8/BC.D3"]
    assert m3["awardable"] is False and m3["achieved"] is False
    assert d3["achieved"] is False
    assert d3["awardable"] is False
    assert d3["dependency_blocked_by"] == "M3"
    assert d3["award_block_reason"] == "dependency_m3_not_met"
    assert d3["award_block_reason_ar"]


def test_invariant_d3_is_never_achieved_while_m3_is_not_awardable(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    scenarios = [
        dict(text=CLAIM_BAD, l4=True, l5=True, teacher=("M3", "D3")),  # M3 blocked by code diff
        dict(text=CLAIM_OK, l4=True, l5=True, teacher=None),           # M3 blocked: no confirmation
        dict(text=CLAIM_OK, l4=False, l5=False, teacher=("M3", "D3")), # M3 blocked: no runtime
        dict(text=CLAIM_OK, l4=False, l5=False, video=True),           # video only
    ]
    for kwargs in scenarios:
        grading, inv = _grading(root, **kwargs)
        by = _finalize(grading, inv, monkeypatch)
        if not (by["8/C.M3"]["achieved"] and by["8/C.M3"].get("awardable") is not False):
            assert not by["8/BC.D3"]["achieved"], kwargs
            assert by["8/BC.D3"]["awardable"] is False, kwargs
        monkeypatch.undo()


def test_d3_stays_achieved_when_m3_is_legitimately_awarded(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True, teacher=("M3", "D3"))
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is True
    assert by["8/BC.D3"]["achieved"] is True
    assert "dependency_blocked_by" not in by["8/BC.D3"]
    assert grading["grade_level"] == "D"


def test_d3_block_is_lifted_and_state_restored_when_m3_later_passes(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=True)  # M3 blocked (no confirmation)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/BC.D3"]["dependency_blocked_by"] == "M3"
    prior_score = by["8/BC.D3"]["pre_gate_state"]["score"]
    monkeypatch.undo()
    record_teacher_confirmation(grading, "M3", confirmed_by="reviewer")
    by = _finalize(grading, inv, monkeypatch)
    d3 = by["8/BC.D3"]
    assert d3["achieved"] is True and d3["awardable"] is True
    assert d3["score"] >= prior_score
    assert "dependency_blocked_by" not in d3 and "pre_gate_state" not in d3


def test_reconciliation_cannot_repromote_a_dependency_blocked_d3(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True, l5=True, teacher=("M3", "D3"))
    _finalize(grading, inv, monkeypatch)
    from app.criteria_result_finalizer import reconcile_authoritative_achieved

    reconcile_authoritative_achieved(grading, artifact_inventory=inv)
    d3 = next(r for r in grading["criteria_results"] if r["criteria_level"] == "8/BC.D3")
    assert d3["achieved"] is False


# ── 4. gameplay video: an evidence path, not awardability ────────────────────
def test_gameplay_video_alone_satisfies_the_evidence_path_but_awards_nothing(versions, monkeypatch):
    inventory = {"runtime_artifacts": {"gamemaker_detected": True}, "gameplay_video_detected": True}
    verdict = evaluate_runtime_evidence(inventory)
    assert verdict["satisfied"] is True
    assert verdict["paths"]["gameplay_video_documented"] is True
    assert verdict["paths"]["runtime_gameplay_validated"] is False  # a video is not a validated run

    grading, inv = _grading(versions, l4=False, l5=False, video=True, teacher=("M3", "D3"))
    monkeypatch.setattr(gate, "evaluate_runtime_evidence", gate.evaluate_runtime_evidence)  # real one
    finalize_grading_criteria_results(grading, artifact_inventory=inv)
    by = {r["criteria_level"]: r for r in grading["criteria_results"]}
    for level in ("8/C.P5", "8/C.P6", "8/C.M3"):
        assert by[level]["achieved"] is False, level
        assert by[level]["awardable"] is False, level
    assert by["8/BC.D3"]["achieved"] is False
    assert grading["grade_level"] == "U"


def test_documentation_states_the_video_vs_runtime_vs_awardability_distinction():
    import app.pro_engine_gameplay_governance as gov

    assert "NOT criterion awardability" in gov.assess_playtest_evidence.__doc__
    assert "not a validated run" in gate.__doc__ or "is NOT this" in gate.__doc__
    assert "awardability" in gate.evaluate_runtime_evidence.__doc__.lower()
