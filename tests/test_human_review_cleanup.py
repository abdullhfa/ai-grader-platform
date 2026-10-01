"""Batch 6: no human-review surface can stop, hold or change the final decision.

Active grading workflow   -> never writes HOLD / human_review_required / HUMAN_REVIEW_REQUIRED,
                             never waits for teacher_confirmed, never blocks an export.
Legacy compatibility/data -> stored fields, contracts and analytics keep loading unchanged.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

import app.secondary_ai_review as sar
from app.assessment_state import compute_assessment_state
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.criterion_authority_guardrails import apply_criterion_authority_guardrails
from app.independent_review import deterministic_review, run_governed_secondary_review
from app.report_feedback_formatter import criterion_report_display
from test_independent_review_governance import (
    COMPARISON, PROVENANCE, FakeReviewer, _base, _core, _row, _review,
    final_result, paused_result,
)

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"


def _app_sources():
    for path in sorted(APP.rglob("*.py")):
        if "calibration" in path.parts:
            continue
        yield path, path.read_text(encoding="utf-8", errors="replace")


# ── 1. no HOLD as a grading state ───────────────────────────────────────────
def test_no_active_code_writes_hold_as_a_grade_decision_status():
    pattern = re.compile(r"""grade_decision_status["']\]\s*=\s*["']HOLD["']""")
    offenders = [str(p.relative_to(ROOT)) for p, s in _app_sources() if pattern.search(s)]
    assert offenders == []


def test_grading_states_are_only_paused_provisional_final():
    seen = set()
    for make in (final_result, paused_result):
        seen.add(compute_assessment_state(make())["state"])
    g = _base([_row("8/C.M3", block=True)], report={"status": "gated"})
    seen.add(g["assessment_state"]["state"])
    assert seen == {"FINAL", "PAUSED", "PROVISIONAL"} and "HOLD" not in seen


@pytest.mark.parametrize("policy", ["hold", "primary", "authoritative"])
def test_reviewer_disagreement_never_creates_hold(monkeypatch, policy):
    monkeypatch.setenv("SECONDARY_REVIEW_DISAGREEMENT_POLICY", policy)  # legacy env is ignored
    g = final_result()
    audit = _review(g, [{"criterion": "M2", "achieved": False, "confidence": 0.8, "reasoning": "x"}])
    assert audit["status"] == "DISAGREEMENT_RECORDED" and audit["hold_required"] is False
    assert g.get("grade_decision_status") in (None, "")
    assert not any(r.get("secondary_review_hold") for r in g["criteria_results"])


def test_the_ui_has_no_hold_or_human_review_banner():
    results = (APP / "templates/batch_results.html").read_text(encoding="utf-8")
    grade = (APP / "templates/batch_grade.html").read_text(encoding="utf-8")
    assert "'HOLD'" not in results and "HOLD — مراجعة بشرية" not in results
    assert "مراجعة بشرية" not in results and "مراجعة بشرية" not in grade
    assert "PAUSED" in results  # the real automated states are still shown


# ── 2. human_review_required cannot stop finalization ────────────────────────
def test_human_review_required_flag_cannot_stop_or_change_finalization():
    plain, flagged = final_result(), final_result()
    flagged["human_review_required"] = True
    flagged["criteria_results"][0]["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"  # legacy data
    finalize_grading_criteria_results(flagged, artifact_inventory=flagged["artifact_inventory"])
    assert flagged["assessment_state"]["state"] == plain["assessment_state"]["state"] == "FINAL"
    assert flagged["assessment_state"]["final_grade_allowed"] is True
    assert deterministic_review(flagged)["decisions"] == deterministic_review(plain)["decisions"]
    assert flagged["grade_level"] == plain["grade_level"]


def test_no_engine_policy_requires_human_review():
    from app.pro_engine_gameplay_governance import get_engine_policy

    for engine in ("godot", "unity", "gamemaker", "unreal", "something_unknown"):
        assert get_engine_policy(engine)["human_review_required"] is False, engine


def test_authority_guardrail_keeps_its_automated_demotion_but_never_asks_a_human():
    g = {"criteria_results": [{"criteria_level": "8/C.P5", "achieved": True, "score": 75, "feedback": "f"}],
         "grade_level": "P", "artifact_inventory": {}}
    report = apply_criterion_authority_guardrails(g, artifact_inventory={})
    row = g["criteria_results"][0]
    assert report["blocked_count"] == 1 and row["achieved"] is False  # automated rule unchanged
    assert row["achievement_authority"] == "RUNTIME_INSUFFICIENT"
    assert report["human_review_required"] is False
    assert report["export_policy"]["allow_export"] is True
    assert "مراجعة بشرية" not in row["feedback"] and "مراجعة بشرية" not in report["summary_ar"]


def test_a_legacy_block_until_review_gate_cannot_block_a_report_export():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    block = src.split('if _export_policy.get("gate") == "block_until_review":')[1][:500]
    assert "HTTPException" not in block and "raise" not in block


def test_active_code_never_writes_the_human_review_authority():
    writers = [
        re.compile(r"""achievement_authority["']\]\s*=\s*["']HUMAN_REVIEW_REQUIRED["']"""),
        re.compile(r"""["']achievement_authority["']\s*:\s*["']HUMAN_REVIEW_REQUIRED["']"""),
        re.compile(r"""\bauthority\s*=\s*["']HUMAN_REVIEW_REQUIRED["']"""),
    ]
    offenders = [str(p.relative_to(ROOT)) for p, s in _app_sources() if any(w.search(s) for w in writers)]
    assert offenders == []


# ── 3. teacher_confirmed ─────────────────────────────────────────────────────
def test_teacher_confirmed_does_not_exist_in_the_application():
    hits = [str(p.relative_to(ROOT)) for p, s in _app_sources() if "teacher_confirmed" in s]
    assert hits == []


def test_teacher_confirmed_has_no_effect_on_the_result():
    a, b = final_result(), final_result()
    b["teacher_confirmed"] = True
    finalize_grading_criteria_results(b, artifact_inventory=b["artifact_inventory"])
    assert _core(a)["assessment_state"]["state"] == _core(b)["assessment_state"]["state"]
    assert b["grade_level"] == a["grade_level"]


# ── 4. AI disagreement creates no human-review gate ──────────────────────────
def test_ai_disagreement_creates_no_human_review_gate():
    g = final_result()
    before = _core(g)
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.99, "reasoning": "x"}])
    assert "human_review_required" not in g
    assert all(r.get("achievement_authority") != "HUMAN_REVIEW_REQUIRED" for r in g["criteria_results"])
    assert g["independent_review"]["auxiliary_ai_review"]["disagreements"]  # recorded, nothing more
    assert _core(g) == before


# ── 5/6. PAUSED stays PAUSED, PROVISIONAL stays non-final ────────────────────
def test_paused_stays_paused_with_legacy_human_review_data_present():
    g = paused_result()
    g["human_review_required"] = True
    g["criteria_results"][0]["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"
    finalize_grading_criteria_results(g, artifact_inventory=g["artifact_inventory"])
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "x"}])
    assert g["assessment_state"]["state"] == "PAUSED" and g["final_grade_allowed"] is False
    assert g["grade_decision_status"] == "PAUSED" and g["official_grade_provisional"] is True


def test_provisional_stays_non_final_after_review():
    g = _base([_row("8/C.M3", block=True)], report={"status": "gated"})
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "x"}])
    assert g["assessment_state"]["state"] == "PROVISIONAL" and g["final_grade_allowed"] is False


# ── 7/8. Batch 5 governance and Batch 4 provenance are unchanged ─────────────
def test_reviewer_is_record_only_and_governance_is_unchanged():
    g = final_result()
    audit = sar.run_secondary_review(
        g, student_text="t", grading_criteria=[], reviewer_provider=FakeReviewer(
            [{"criterion": "M2", "achieved": False, "confidence": 0.8, "reasoning": "x"}]),
        force_enabled=True)
    assert audit["authority"] == "AUXILIARY" and audit["effect_on_grade"] == "none"
    for key in ("grade_decision_status", "official_grade_provisional", "human_review_required"):
        assert key not in g
    det = deterministic_review(g)
    assert det["authority"] == "DETERMINISTIC" and det["final_decision"] is True


def test_provenance_and_version_comparison_are_untouched():
    g = paused_result()
    inv_before = copy.deepcopy(g["artifact_inventory"])
    _review(g, [{"criterion": "M3", "achieved": True, "confidence": 0.9, "reasoning": "x"}])
    apply_criterion_authority_guardrails(g, artifact_inventory=g["artifact_inventory"])
    rep = g["artifact_inventory"]["runtime_observation_report"]
    assert rep["provenance"] == PROVENANCE and rep["version_runtime_comparison"] == COMPARISON
    assert g["artifact_inventory"] == inv_before


# ── legacy compatibility/data keeps working ──────────────────────────────────
def test_legacy_stored_authority_still_renders_without_a_human_review_claim():
    icon, text, *_ = criterion_report_display({"achievement_authority": "HUMAN_REVIEW_REQUIRED"})
    assert icon == "⏸" and "مراجعة بشرية" not in text and "Human Review" not in text


def test_legacy_governance_decision_contract_still_loads():
    from app.governance_decision import GovernanceDecisionSnapshot

    snap = GovernanceDecisionSnapshot()  # stored/legacy contract is intact
    assert snap.human_review_required is True and snap.is_final is False


def test_legacy_lineage_hold_key_is_kept_for_stored_data_but_not_a_human_request():
    from app import evidence_lineage as el

    src = (APP / "evidence_lineage.py").read_text(encoding="utf-8")
    assert '"HOLD"' in src  # analytics key preserved for old snapshots
    assert "human_review_required" not in src
    assert hasattr(el, "attach_evidence_lineage_to_snapshot")
