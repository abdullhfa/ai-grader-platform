from app.batch_grader import _initial_submission_paths, _video_keyframe_limits
from app.gameplay_verifier import (
    _test_document_present,
    build_gameplay_verification_summary,
    format_agent_play_summary_ar,
)
from app.requirement_checklist import build_requirement_checklist
from app.runtime_evidence_gate import (
    BTECCriterionMapper,
    _align_overall_feedback_after_runtime_open,
)
from app.report_feedback_formatter import (
    build_runtime_outcome,
    clean_report_text,
    criterion_decision_matrix_for_report,
    format_criterion_feedback_for_report,
    format_score_fraction_ar,
    normalize_agent_play_label_ar,
    sanitize_strengths_for_runtime,
)
from app.gameplay_semantic_verification import assess_gameplay_semantics


def _confidence(requirement: str, verified: bool):
    return {
        "requirement": requirement,
        "verified": verified,
        "confidence_source": "runtime_l4",
    }


def test_arabic_brief_extracts_all_required_gamemaker_mechanics():
    checklist = build_requirement_checklist(
        student_text=(
            "يجب تحريك اللاعب وجمع العناصر وتجنب المخاطر، وتزيد النقاط عند الجمع. "
            "يستهلك الاصطدام الأرواح، واللعبة مؤقتة ولها مستويات صعوبة. "
            "توجد شاشة خسارة وإعادة تشغيل."
        )
    )

    assert {
        "player_movement",
        "collect_items",
        "enemy_interaction",
        "score_system",
        "lives_system",
        "timer_system",
        "difficulty_levels",
        "lose_condition",
        "restart",
    }.issubset(set(checklist["requirement_ids"]))


def test_gate_lists_lives_timer_and_difficulty_when_required_but_unverified():
    required = ["player_movement", "lives_system", "timer_system", "difficulty_levels"]
    verification = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "mechanics_verified_count": 4,
        "player_movement_verified": True,
        "requirement_checklist": {
            "requirements": [
                {"id": req_id, "applicability": "required"} for req_id in required
            ]
        },
        "runtime_evidence_package": {
            "requirement_confidence": [
                _confidence("player_movement", True),
                _confidence("lives_system", False),
                _confidence("timer_system", False),
                _confidence("difficulty_levels", False),
            ]
        },
    }

    result = BTECCriterionMapper(grading_mode="PRO").evaluate(
        verification,
        test_doc_entries=1,
        engine_id="gamemaker",
    )

    assert result["required_feature_verification"]["missing"] == [
        "lives_system",
        "timer_system",
        "difficulty_levels",
    ]
    assert result["criterion_pass"]["P5"] is False
    assert result["criterion_pass"]["P6"] is False


def test_terminal_feedback_never_claims_rejected_p5_p6_were_awarded():
    result = {
        "grade_level": "U",
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False},
            {"criteria_level": "8/C.P6", "achieved": False},
        ],
        "overall_feedback": "تم اعتماد C.P5 وC.P6",
    }

    _align_overall_feedback_after_runtime_open(result)

    assert "تم اعتماد C.P5 وC.P6" not in result["overall_feedback"]
    assert "لم تُعتمد معايير التشغيل" in result["overall_feedback"]


def test_l4_label_does_not_invent_jump_score_or_open_gate():
    label = format_agent_play_summary_ar(
        "L4", {"gameplay_entered": True, "l4_level": "L4_full"}
    )

    assert "قفز" not in label
    assert "نقاط" not in label
    assert "Gate مفتوح" not in label
    assert "L4 كامل" not in label
    assert "لا يعني ذلك اكتمال اللعبة" in label


def test_report_runtime_outcome_uses_feature_gate_not_legacy_mechanic_count():
    checklist = {
        "requirements": [
            {"id": "player_movement", "applicability": "required"},
            {"id": "score_system", "applicability": "required"},
        ]
    }
    package = {
        "requirement_confidence": [
            _confidence("player_movement", True),
            _confidence("score_system", False),
        ]
    }
    gv = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "mechanics_verified_count": 4,
        "player_movement_verified": True,
    }
    summary = build_gameplay_verification_summary(
        inventory={
            "gameplay_verification": gv,
            "requirement_checklist": checklist,
            "runtime_evidence_package": package,
        },
        grading_result={
            "grading_mode": "PRO",
            "gameplay_verification": gv,
            "requirement_checklist": checklist,
            "runtime_evidence_package": package,
        },
    )

    assert summary["runtime_outcome"]["criterion_pass_p5"] is False
    assert "Gate مفتوح" not in summary["agent_play_label_ar"]


def test_pro_profile_allocates_video_keyframes():
    per_video, total, max_videos = _video_keyframe_limits(
        fast_mode=False, grading_mode="PRO"
    )

    assert per_video > 0
    assert total >= per_video
    assert max_videos >= 1


def test_vision_resolves_submission_paths_before_later_pipeline_stages():
    info = {
        "path": "student/report.docx",
        "submission_paths": ["student/report.docx", "student/play.mp4"],
    }

    assert _initial_submission_paths(info) == [
        "student/report.docx",
        "student/play.mp4",
    ]
    assert _initial_submission_paths({"path": "student/report.docx"}) == [
        "student/report.docx"
    ]


def test_runtime_report_uses_actual_gate_reason_after_l4_gameplay():
    outcome = build_runtime_outcome(
        {"gameplay_entered": True, "l4_level": "L4_full"},
        {
            "criterion_pass": {"P5": False, "P6": False},
            "decisions": [
                {
                    "criterion": "P5",
                    "reason_ar": "لم تثبت الميزات المطلوبة: score_system, restart",
                },
                {
                    "criterion": "P6",
                    "reason_ar": "لم تثبت الميزات المطلوبة: score_system, restart",
                },
            ],
        },
        engine_id="gamemaker",
    )

    impact = "\n".join(outcome["impact_cp5_cp6_ar"])
    assert "score_system, restart" in impact
    assert "يتطلب gameplay L4" not in impact


def test_teacher_report_hides_internal_runtime_reason_token():
    assert "runtime_l4_verified_override" not in clean_report_text(
        "reason=runtime_l4_verified_override"
    )


def test_teacher_report_drops_strength_that_contradicts_runtime():
    strengths = [
        "إظهار القدرة على استخدام GameMaker لإنشاء لعبة قابلة للتشغيل.",
        "تنفيذ حركة اللاعب ونظام بسيط للأرواح.",
    ]
    result = {
        "runtime_evidence_package": {
            "requirement_confidence": [
                {"requirement": "player_movement", "verified": True},
                {"requirement": "lives_system", "verified": False},
            ]
        }
    }

    assert sanitize_strengths_for_runtime(strengths, result) == [strengths[0]]


def test_blocked_criterion_report_prefers_terminal_gate_reason():
    rendered = format_criterion_feedback_for_report(
        "تعليق قديم: ميزات اللعبة ناقصة",
        runtime_note_ar="يتطلب وثائق اختبار منهجية (موجود: 0)",
        achieved=False,
        awardable=False,
    )

    assert "وثائق اختبار منهجية" in rendered
    assert "تعليق قديم" not in rendered


def test_blocked_runtime_matrix_does_not_overstate_source_snippets():
    criteria = {
        "criteria_level": "8/C.P5",
        "achieved": False,
        "runtime_gate_block": True,
        "award_block_reason_ar": "ميزات مطلوبة غير مثبتة: score_system, restart",
        "decision_matrix": [
            {
                "requirement": "C.P5/8",
                "met": False,
                "evidence": "mylives=mylives-1 دليل كامل على الأرواح",
            }
        ],
    }

    matrix = criterion_decision_matrix_for_report(criteria)
    assert matrix == [
        {
            "requirement": "C.P5/8",
            "met": False,
            "evidence": "ميزات مطلوبة غير مثبتة: score_system, restart",
        }
    ]


def test_arabic_score_fraction_is_unambiguous_in_rtl():
    assert format_score_fraction_ar(23, 100) == "23 من 100"


def test_legacy_l4_full_label_is_normalized_for_old_snapshots():
    label = normalize_agent_play_label_ar(
        "نعم — L4 كامل (حركة + قفز/نقاط — Gate مفتوح)"
    )
    assert "L4 كامل" not in label
    assert "لا يعني ذلك اكتمال اللعبة" in label


def test_general_word_report_is_not_counted_as_cp6_test_document():
    inventory = {
        "submission_paths": ["student/general_report.docx"],
        "assets_detected": {"word_pdf": True, "testing_documentation": False},
    }

    assert _test_document_present(inventory) is False


def test_named_test_plan_is_cp6_test_document():
    assert _test_document_present(
        {"submission_paths": ["student/test_plan.docx"]}
    ) is True


def test_semantics_accepts_verified_loss_without_inventing_win():
    observation = {
        "runtime_observed": True,
        "gameplay_verification": {
            "requirement_results": [
                {"req_id": "lose_condition", "verified": True},
            ]
        },
    }

    semantics = assess_gameplay_semantics(observation)
    assert semantics["fail_state_detected"] is True
    assert semantics["win_state_detected"] is False
