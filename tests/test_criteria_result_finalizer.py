"""Criteria finalizer — deliverable Godot pass + feedback sync."""
from __future__ import annotations

from app.btec_criteria_governance import enforce_not_achieved_feedback_consistency
from app.criteria_result_finalizer import finalize_grading_criteria_results


def test_resolve_assets_from_feedback_mentions_exe():
    from app.criteria_result_finalizer import _resolve_assets

    gr = {
        "criteria_results": [
            {
                "criteria_level": "8/C.P5",
                "feedback": "farst game.exe و final.apk و Godot GDScript في PLAYER.gd",
                "covered_points": ["test"],
                "missing_points": [],
            }
        ],
    }
    assets = _resolve_assets(gr, {})
    assert assets["has_exe"]
    assert assets["has_src"]


def test_reconcile_fixes_score_75_achieved_false():
    from app.criteria_result_finalizer import reconcile_authoritative_achieved

    gr = {
        "student_text": "PLAYER.gd و farst game.exe و final.apk وجدول اختبار",
        "criteria_results": [
            {
                "criteria_level": "8/C.P5",
                "achieved": False,
                "score": 75,
                "feedback": "⚠️ [حوكمة BTEC] لم يتحقق...\n\n[تحليل الذكاء الاصطناعي — غير معتمد]\nتم تحقيق المعيار بالكامل. final.exe",
                "deterministic_rubric": {
                    "deterministic_achieved": True,
                    "verdict_status": "pass",
                    "authority": "RUNTIME_VALIDATION",
                },
                "decision_matrix": [{"met": False, "reasoning": "تم تحقيق المعيار بالكامل."}],
            },
        ],
    }
    changes = reconcile_authoritative_achieved(gr)
    row = gr["criteria_results"][0]
    assert row["achieved"] is True
    feedback = str(row.get("feedback") or "")
    assert "لم يتحقق المعيار مؤسسياً" not in feedback
    assert changes


def _p5_p6_gr():
    return {
        "student_text": "في ملف PLAYER.gd استخدمنا GDScript مع Godot. جدول اختبار يوضح 8 حالات.",
        "grade_level": "U",
        "criteria_results": [
            {
                "criteria_level": "8/C.P5",
                "achieved": False,
                "score": 0,
                "feedback": "تم تحقيق المعيار بالكامل. final.exe و final.pck مرفقة.",
                "covered_points": ["godot"],
                "missing_points": [],
            },
            {
                "criteria_level": "8/C.P6",
                "achieved": False,
                "score": 0,
                "feedback": "تم تحقيق المعيار بشكل ممتاز. جدول اختبار واستبيان.",
                "covered_points": ["tests"],
                "missing_points": [],
            },
        ],
        "evidence_completeness_gate": {
            "assets_detected": {"executable": True, "source_code": True, "word_pdf": True},
        },
    }


def test_finalize_promotes_p5_p6_with_exe_and_runtime_evidence():
    """Exe + positive AI + REAL runtime evidence (gameplay video) → promote stands."""
    gr = _p5_p6_gr()
    inv = {
        "has_executable_artifacts": True,
        "has_source_code_artifacts": True,
        "documentation": {"files": [{"name": "report.docx"}]},
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        # Accepted runtime evidence — documented gameplay video.
        "gameplay_video_detected": True,
    }
    out = finalize_grading_criteria_results(gr, artifact_inventory=inv)
    assert out["change_count"] >= 2
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    assert by["8/C.P5"]["achieved"] is True
    assert by["8/C.P6"]["achieved"] is True
    p5_score = by["8/C.P5"]["score"]
    assert isinstance(p5_score, (int, float))
    assert p5_score >= 75


def test_finalize_blocks_p5_p6_with_exe_but_no_runtime_evidence():
    """Runtime Gate: exe + excellent docs but NO runtime/video/L5 → NOT awarded."""
    gr = _p5_p6_gr()
    inv = {
        "has_executable_artifacts": True,
        "has_source_code_artifacts": True,
        "documentation": {"files": [{"name": "report.docx"}]},
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        # No gameplay video, no runtime PASS, no L5 playtest.
    }
    finalize_grading_criteria_results(gr, artifact_inventory=inv)
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    assert by["8/C.P5"]["achieved"] is False
    assert by["8/C.P5"]["awardable"] is False
    assert by["8/C.P5"]["runtime_gate_block"] is True
    assert by["8/C.P6"]["achieved"] is False
    assert by["8/C.P6"]["runtime_gate_block"] is True
    gate = gr.get("runtime_evidence_gate") or {}
    assert gate.get("runtime_status") == "BLOCKED"
    assert gr["grade_level"] == "U"


def test_not_achieved_feedback_aligned_arabic():
    rows = [
        {
            "criteria_level": "8/C.P5",
            "achieved": False,
            "score": 0,
            "feedback": "تم تحقيق المعيار بالكامل.",
            "deterministic_rubric": {"reason": "missing_evidence:source_code"},
        }
    ]
    changes = enforce_not_achieved_feedback_consistency(rows)
    assert changes
    assert "لم يتحقق المعيار مؤسسياً" in rows[0]["feedback"]
