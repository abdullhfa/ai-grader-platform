"""Regression tests: the runtime gate is fully automated and fails CLOSED.

1. gate exception  → no runtime-dependent award survives; status NOT_VERIFIED (no human review)
2. no human step   → no teacher confirmation anywhere; L5 is neither required nor a confirmation
3. M3 blocked      → D3 blocked at the *row* level (``dependency_blocked_by``)
4. video only      → an evidence PATH, not criterion awardability
5. evidence change → new/changed files are re-read (RESUME), vanished files keep the old verdict
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import app.runtime_evidence_gate as gate
from app.criteria_result_finalizer import finalize_grading_criteria_results
from app.runtime_evidence_gate import (
    apply_runtime_gate_fail_closed,
    evaluate_runtime_evidence,
)
from app.version_code_diff import evaluate_m3_code_diff
from test_uniform_m3_d3_governance import (
    FULL_L4,
    _academic_row,
    _gamemaker_versions,
    _write,
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


def _grading(root: Path, *, text=CLAIM_OK, l4=True, l5=False, video=False):
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


def test_gate_exception_is_recorded_as_not_verified_without_asking_for_a_human(versions, monkeypatch):
    grading, inv = _grading(versions, l4=False)
    _finalize(grading, inv, monkeypatch, raises=True)
    err = grading["runtime_gate_error"]
    assert err["status"] == "NOT_VERIFIED"
    assert err["error_type"] == "RuntimeError"
    assert "simulated gate crash" in err["error"]
    assert set(err["blocked"]) == {"8/C.P5", "8/C.P6", "8/C.M3", "8/BC.D3"}
    assert grading["grade_decision_status"] == "NOT_VERIFIED"
    assert grading["official_grade_provisional"] is True
    assert grading["evidence_required"] == "AUTOMATED_VERIFICATION_INCOMPLETE"
    # fully automated: nothing may wait on, or ask for, a human
    assert not grading.get("human_review_required")
    assert grading["grade_decision_status"] != "HOLD"
    assert grading["criteria_finalizer"]["changes"]  # the block is auditable
    assert "يدوي" not in gate._GATE_ERROR_REASON_AR and "بشري" not in gate._GATE_ERROR_REASON_AR


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
    apply_runtime_gate_fail_closed({"criteria_results": "nope"}, ValueError("x"))
    apply_runtime_gate_fail_closed({}, ValueError("x"))


def test_a_later_healthy_gate_clears_the_error_and_reevaluates(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True)
    _finalize(grading, inv, monkeypatch, raises=True)
    assert "runtime_gate_error" in grading
    monkeypatch.undo()  # gate healthy again
    by = _finalize(grading, inv, monkeypatch)
    assert "runtime_gate_error" not in grading
    assert grading.get("grade_decision_status") != "NOT_VERIFIED"
    assert "evidence_required" not in grading
    assert by["8/C.M3"]["achieved"] is True  # M3 re-opens on its own automated evidence
    assert by["8/BC.D3"]["achieved"] is True  # restored: M3 passes again


def test_internal_l4_evaluation_error_is_fail_closed_and_visible(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True)
    monkeypatch.setattr(
        "app.gameplay_verifier.assess_automated_l4_gate",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("l4 crash")),
    )
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.P5"]["achieved"] is False
    assert by["8/C.M3"]["achieved"] is False
    assert "l4 crash" in grading["runtime_evidence_gate"]["automated_l4_gate"]["error"]


def test_the_ui_renders_not_verified_as_automated_incomplete_not_human_review():
    html = Path("app/templates/batch_results.html").read_text(encoding="utf-8")
    block = html[html.index("grade_decision_status == 'NOT_VERIFIED'"):][:400]
    assert "التحقق الآلي غير مكتمل" in block
    assert "بشرية" not in block


# ── 2. fully automated: no human confirmation anywhere ───────────────────────
def test_the_teacher_confirmation_api_is_gone():
    for name in ("record_teacher_confirmation", "read_teacher_confirmations", "TEACHER_CONFIRMABLE"):
        assert not hasattr(gate, name), name


def test_m3_opens_from_automated_evidence_without_l5_or_any_human_step(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True, l5=False)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is True
    assert by["8/C.M3"]["achievement_authority"] == "AUTOMATED_RUNTIME_GATE"
    assert by["8/BC.D3"]["achieved"] is True
    assert grading["grade_level"] == "D"
    assert "teacher_confirmations" not in grading
    assert not grading.get("human_review_required")


def test_a_completed_l5_playtest_changes_nothing_for_m3(tmp_path, monkeypatch):
    results = []
    for l5 in (False, True):
        root = _gamemaker_versions(tmp_path / f"l5_{l5}", v2_step=V2_OK)
        grading, inv = _grading(root, l4=True, l5=l5)
        by = _finalize(grading, inv, monkeypatch)
        results.append((by["8/C.M3"]["achieved"], by["8/BC.D3"]["achieved"], grading["grade_level"]))
        monkeypatch.undo()
    assert results[0] == results[1] == (True, True, "D")


def test_l5_alone_never_opens_m3_without_automated_runtime_and_diff(versions, monkeypatch):
    grading, inv = _grading(versions, l4=False, l5=True)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.P5"]["achieved"] is False
    assert by["8/C.M3"]["achieved"] is False
    assert by["8/BC.D3"]["achieved"] is False


def test_missing_evidence_means_blocked_not_waiting_for_a_human(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True)
    by = _finalize(grading, inv, monkeypatch)
    m3 = by["8/C.M3"]
    assert m3["achieved"] is False and m3["awardable"] is False
    assert "human" not in str(m3.get("award_block_reason", "")).lower()
    assert not grading.get("human_review_required")
    decisions = {d["criterion"]: d for d in grading["runtime_evidence_gate"]["automated_l4_gate"]["decisions"]}
    assert decisions["M3"]["reason"] == "m3_code_diff_improvements_mostly_unsupported"


# ── 3. D3 depends on M3 at the row level ─────────────────────────────────────
def test_d3_is_blocked_on_its_own_row_when_m3_is_blocked(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True)
    by = _finalize(grading, inv, monkeypatch)
    m3, d3 = by["8/C.M3"], by["8/BC.D3"]
    assert m3["awardable"] is False and m3["achieved"] is False
    assert d3["achieved"] is False
    assert d3["awardable"] is False
    assert d3["dependency_blocked_by"] == "M3"
    assert d3["award_block_reason"] == "dependency_m3_not_met"
    assert d3["award_block_reason_ar"]


def test_invariant_d3_is_never_achieved_while_m3_is_not_awardable(tmp_path, monkeypatch):
    scenarios = [
        dict(text=CLAIM_BAD, l4=True),               # M3 blocked by code diff
        dict(text=CLAIM_OK, l4=False, l5=True),      # M3 blocked: no automated runtime
        dict(text=CLAIM_OK, l4=False, video=True),   # video only
    ]
    for i, kwargs in enumerate(scenarios):
        root = _gamemaker_versions(tmp_path / str(i), v2_step=V2_OK)
        grading, inv = _grading(root, **kwargs)
        by = _finalize(grading, inv, monkeypatch)
        assert not (by["8/BC.D3"]["achieved"] and not by["8/C.M3"]["achieved"]), kwargs
        assert by["8/BC.D3"]["awardable"] is False, kwargs
        monkeypatch.undo()


def test_d3_stays_achieved_when_m3_is_legitimately_awarded(versions, monkeypatch):
    grading, inv = _grading(versions, l4=True)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is True
    assert by["8/BC.D3"]["achieved"] is True
    assert "dependency_blocked_by" not in by["8/BC.D3"]
    assert grading["grade_level"] == "D"


def test_d3_block_is_lifted_and_state_restored_when_m3_later_passes(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/BC.D3"]["dependency_blocked_by"] == "M3"
    prior_score = by["8/BC.D3"]["pre_gate_state"]["score"]
    monkeypatch.undo()
    grading["student_text"] = CLAIM_OK  # the missing evidence arrives → re-evaluated automatically
    by = _finalize(grading, inv, monkeypatch)
    d3 = by["8/BC.D3"]
    assert by["8/C.M3"]["achieved"] is True
    assert d3["achieved"] is True and d3["awardable"] is True
    assert d3["score"] >= prior_score
    assert "dependency_blocked_by" not in d3 and "pre_gate_state" not in d3


def test_reconciliation_cannot_repromote_a_dependency_blocked_d3(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, text=CLAIM_BAD, l4=True)
    _finalize(grading, inv, monkeypatch)
    from app.criteria_result_finalizer import reconcile_authoritative_achieved

    reconcile_authoritative_achieved(grading, artifact_inventory=inv)
    d3 = next(r for r in grading["criteria_results"] if r["criteria_level"] == "8/BC.D3")
    assert d3["achieved"] is False


# ── 4. gameplay video: an evidence path, not awardability ────────────────────
def test_gameplay_video_alone_satisfies_the_evidence_path_but_awards_nothing(versions):
    inventory = {"runtime_artifacts": {"gamemaker_detected": True}, "gameplay_video_detected": True}
    verdict = evaluate_runtime_evidence(inventory)
    assert verdict["satisfied"] is True
    assert verdict["paths"]["gameplay_video_documented"] is True
    assert verdict["paths"]["runtime_gameplay_validated"] is False  # a video is not a validated run

    grading, inv = _grading(versions, l4=False, l5=False, video=True)
    finalize_grading_criteria_results(grading, artifact_inventory=inv)  # the real gate
    by = {r["criteria_level"]: r for r in grading["criteria_results"]}
    for level in ("8/C.P5", "8/C.P6", "8/C.M3"):
        assert by[level]["achieved"] is False, level
        assert by[level]["awardable"] is False, level
    assert by["8/BC.D3"]["achieved"] is False
    assert grading["grade_level"] == "U"


def test_documentation_states_the_video_vs_runtime_vs_awardability_distinction():
    import app.pro_engine_gameplay_governance as gov

    assert "NOT criterion awardability" in gov.assess_playtest_evidence.__doc__
    assert "is NOT this" in gate.__doc__
    assert "awardability" in gate.evaluate_runtime_evidence.__doc__.lower()


# ── 5. evidence changes are re-read (RESUME); vanished files keep the verdict ──
def test_new_or_changed_evidence_is_never_answered_from_a_stale_result(tmp_path):
    root = tmp_path / "student"
    for design, ver, code in (("D1", "V1", "spd = 4;\n"), ("D2", "V2", "spd = 4;\n")):
        _write(root / design / "code/Game.yyp", "{}")
        _write(root / design / "code/o/Step_0.gml", code)
        (root / design / ver).mkdir(parents=True)
    first = evaluate_m3_code_diff([], CLAIM_OK, root=root)
    assert first["ok"] is False and first["status"] == "no_code_change"

    # the improved V2 arrives later → same root, same text, changed files
    _write(root / "D2" / "code/o/Step_0.gml", "spd = 6;\n")
    second = evaluate_m3_code_diff([], CLAIM_OK, root=root)
    assert second["ok"] is True and second["status"] == "supported"


def test_previous_verdict_is_kept_only_when_the_files_are_gone(tmp_path, monkeypatch):
    root = _gamemaker_versions(tmp_path, v2_step=V2_OK)
    grading, inv = _grading(root, l4=True)
    by = _finalize(grading, inv, monkeypatch)
    assert by["8/C.M3"]["achieved"] is True and grading["m3_code_diff"]["ok"] is True
    monkeypatch.undo()

    shutil.rmtree(root)  # student files cleaned up after grading
    by = _finalize(grading, inv, monkeypatch)
    assert grading["m3_code_diff"]["status"] == "supported"  # earlier verdict retained
    assert by["8/C.M3"]["achieved"] is True
